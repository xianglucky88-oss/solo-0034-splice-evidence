import json
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request
from pathlib import Path

from splice.codec import pack
from splice.db import Database
from splice.server import serve
from tools.review_check import PLAN, A, b


def request(base, path, payload=None, status=200):
    data = pack(payload) if payload is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    target = Request(base + path, data=data, headers=headers)
    try:
        response = urlopen(target, timeout=8)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        if response.status != status:
            raise RuntimeError(f'{path} 预期 {status} 实际 {response.status}: {raw[:200]!r}')
        return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw


from urllib.request import urlopen


def main():
    with TemporaryDirectory() as folder:
        db = Path(folder) / 'edge.sqlite3'
        with serve(Database(db), 0) as server:
            t = Thread(target=server.serve_forever); t.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                api = '/api/splice/spans/RV-W1'
                request(base, '/api/splice/spans', PLAN)
                request(base, api + '/traces', A)
                traces = [b('B-301', [200, 220, 150], 420), b('B-302', [200, 380, 160], 580),
                          b('B-304', [205, 225, 155], 430)]
                for tr in traces:
                    request(base, api + '/traces', tr)

                # 1. review workspace without any counter selected -> 409
                roster = {'revision': 0, 'direction': 'b', 'tolerance_mdb': 10,
                          'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}, {'trace_id': 'B-304'}]}
                request(base, api + '/rosters', roster)
                request(base, api, None, 409)

                # 2. select counter A -> review ready, issue legacy traceability still works
                request(base, api + '/selection', {'revision': 1, 'a': 'A-1', 'b': None})
                work = request(base, api)
                assert work['mode'] == 'review' and work['budget']['status'] == 'ready'
                rel = request(base, api + '/releases', {'revision': 2})
                assert rel['snapshot']['mode'] == 'review'

                # 3. clear roster then do a legacy release on same span
                request(base, api + '/rosters/clear', {'revision': 2, 'direction': 'b'})
                request(base, api + '/selection', {'revision': 3, 'a': 'A-1', 'b': 'B-301'})
                legacy = request(base, api)
                assert legacy['mode'] == 'legacy'
                rel_legacy = request(base, api + '/releases', {'revision': 4})
                assert rel_legacy['snapshot']['ruleset'] == 'splice-closure-v1'

                # 4. compare across modes must be rejected with 409
                request(base, api + '/compare/2/4', None, 409)

                # 5. old review release still fully traceable after returning to legacy
                archived = request(base, api + '/releases/2')
                assert archived['snapshot']['review']['group'] == ['B-301', 'B-304']
                arc_ev = request(base, api + '/releases/2/evidence/B-304/B-304-1')
                assert arc_ev['event']['loss_mdb'] == 205
                csvdata = request(base, api + '/releases/2/sites.csv').decode()
                assert 'B-304' in csvdata

                # 6. roster cannot reference >9 / <3 or unknown trace
                big = {'revision': 4, 'direction': 'b', 'tolerance_mdb': 5,
                       'traces': [{'trace_id': f'X-{i}'} for i in range(10)]}
                request(base, api + '/rosters', big, 422)
                request(base, api + '/rosters',
                        {**roster, 'revision': 4, 'traces': roster['traces'][:2]}, 422)
                unknown = {'revision': 4, 'direction': 'b', 'tolerance_mdb': 5,
                           'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}, {'trace_id': 'NOPE'}]}
                request(base, api + '/rosters', unknown, 404)

                # 7. stale revision on roster save
                request(base, api + '/rosters', {**roster, 'revision': 99}, 409)
                print('EDGE CASES PASSED')
            finally:
                server.shutdown(); t.join()


if __name__ == '__main__':
    main()
