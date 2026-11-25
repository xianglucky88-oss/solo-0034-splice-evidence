import json
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request
from pathlib import Path

from splice.codec import pack
from splice.db import Database
from splice.server import serve


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
            raise RuntimeError(f'{path} 预期 HTTP {status}，实际 {response.status}: {raw[:300]!r}')
        return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw


from urllib.request import urlopen

PLAN = {
    "span_id": "RV-W1", "label": "复核段", "a_label": "甲端", "b_label": "乙端",
    "length_mm": 1600000, "fixed_mdb": 100, "link_limit_mdb": 5000, "residual_limit_mdb": 2000,
    "sites": [
        {"site_id": "J01", "at_mm": 360000, "window_mm": 30000, "limit_mdb": 1000},
        {"site_id": "J02", "at_mm": 810000, "window_mm": 30000, "limit_mdb": 1000},
        {"site_id": "J03", "at_mm": 1270000, "window_mm": 30000, "limit_mdb": 1000}
    ]
}

A = {"trace_id": "A-1", "direction": "a", "near_mm": 10000, "far_mm": 1610000, "total_mdb": 300,
     "events": [
         {"event_id": "a1", "at_mm": 370000, "loss_mdb": 100},
         {"event_id": "a2", "at_mm": 820000, "loss_mdb": 120},
         {"event_id": "a3", "at_mm": 1280000, "loss_mdb": 110}]}

# B repeats: positions must mirror to the 3 windows. near 20000 far 1620000
def b(tid, losses, total):
    return {"trace_id": tid, "direction": "b", "near_mm": 20000, "far_mm": 1620000, "total_mdb": total,
            "events": [
                {"event_id": tid + "-1", "at_mm": 1268000, "loss_mdb": losses[0]},
                {"event_id": tid + "-2", "at_mm": 812000, "loss_mdb": losses[1]},
                {"event_id": tid + "-3", "at_mm": 352000, "loss_mdb": losses[2]}]}


def main():
    with TemporaryDirectory() as folder:
        db = Path(folder) / 'rv.sqlite3'
        with serve(Database(db), 0) as server:
            t = Thread(target=server.serve_forever); t.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                api = '/api/splice/spans/RV-W1'
                request(base, '/api/splice/spans', PLAN)
                request(base, api + '/traces', A)
                b1 = b('B-301', [200, 220, 150], 420)
                b2 = b('B-302', [200, 380, 160], 580)
                b3 = b('B-303', [360, 220, 170], 580)
                b4 = b('B-304', [205, 225, 155], 430)
                for tr in (b1, b2, b3, b4):
                    request(base, api + '/traces', tr)
                # A-side single adoption (the other end)
                request(base, api + '/selection', {'revision': 0, 'a': 'A-1', 'b': None})
                # workspace before roster: legacy held
                work = request(base, api)
                assert work['mode'] == 'legacy', work['mode']
                # roster without counter on opposite side? counter A selected already -> fine
                bad_roster = {'revision': 1, 'direction': 'b', 'tolerance_mdb': 10,
                              'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}]}
                request(base, api + '/rosters', bad_roster, 422)  # fewer than 3
                dup = {'revision': 1, 'direction': 'b', 'tolerance_mdb': 10,
                       'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-301'}, {'trace_id': 'B-302'}]}
                request(base, api + '/rosters', dup, 422)  # duplicate
                wrong_dir = {'revision': 1, 'direction': 'a', 'tolerance_mdb': 10,
                             'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}, {'trace_id': 'B-303'}]}
                request(base, api + '/rosters', wrong_dir, 422)
                roster = {'revision': 1, 'direction': 'b', 'tolerance_mdb': 10,
                          'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}, {'trace_id': 'B-303'}]}
                saved = request(base, api + '/rosters', roster)
                assert saved['changed'] is True and saved['revision'] == 2, saved
                # idempotent resubmit -> no new revision
                again = request(base, api + '/rosters', {**roster, 'revision': 2})
                assert again['changed'] is False and again['revision'] == 2
                work = request(base, api)
                assert work['mode'] == 'review' and work['review_direction'] == 'b'
                rev = work['review']
                print('scenario1 group:', rev['group'], 'blockers:', rev['blockers'])
                assert rev['group'] == [] and rev['blockers'] == ['review_no_majority'], rev['blockers']
                assert work['budget']['status'] == 'held'
                # issue must be refused
                request(base, api + '/releases', {'revision': 2}, 409)
                # rosters read endpoint
                got = request(base, api + '/rosters')
                assert [x['trace_id'] for x in got['b']] == ['B-301', 'B-302', 'B-303']
                assert all(x['tolerance_mdb'] == 10 for x in got['b'])
                # swap B-303 -> B-304 with confirmation revision
                roster2 = {'revision': 2, 'direction': 'b', 'tolerance_mdb': 10,
                           'traces': [{'trace_id': 'B-301'}, {'trace_id': 'B-302'}, {'trace_id': 'B-304'}]}
                saved2 = request(base, api + '/rosters', roster2)
                assert saved2['revision'] == 3
                work = request(base, api)
                rev = work['review']
                print('scenario2 group:', rev['group'], 'blockers:', rev['blockers'])
                assert rev['group'] == ['B-301', 'B-304'], rev['group']
                assert rev['blockers'] == [] and work['budget']['status'] == 'ready'
                # exclusions recorded
                excl = {x['trace_id']: x['exclusion'] for x in rev['roster'] if x['exclusion']}
                assert set(excl) == {'B-302'} and excl['B-302']['code'] == 'outside_largest_group'
                # members have full closure results
                for mid in rev['group']:
                    m = rev['members'][mid]
                    assert m['status'] == 'ready' and len(m['sites']) == 3
                    assert all(s['status'] == 'pass' for s in m['sites'])
                # issue release
                rel = request(base, api + '/releases', {'revision': 3})
                assert rel['snapshot']['ruleset'] == 'splice-review-v1'
                assert rel == request(base, api + '/releases', {'revision': 3})
                # evidence inside review snapshot works
                ev = request(base, api + '/evidence/B-301/B-301-1')
                assert ev['event']['event_id'] == 'B-301-1'
                # archived evidence
                arc = request(base, api + '/releases/3/evidence/B-304/B-304-1')
                assert arc['event']['trace_id'] == 'B-304'
                # CSV export
                csvdata = request(base, api + '/releases/3/sites.csv').decode('utf-8')
                assert 'B-301' in csvdata and 'B-304' in csvdata and 'B-302' not in csvdata
                print(csvdata)
                # compare same-mode releases: create second review release after tolerance change
                roster3 = request(base, api + '/rosters',
                                  {**roster2, 'revision': 3, 'tolerance_mdb': 12})
                assert roster3['revision'] == 4
                rel2 = request(base, api + '/releases', {'revision': 4})
                cmp = request(base, api + '/compare/3/4')
                assert cmp['mode'] == 'review'
                print('compare keys:', cmp.keys())
                # clear roster -> back to legacy mode
                cleared = request(base, api + '/rosters/clear', {'revision': 4, 'direction': 'b'})
                assert cleared['revision'] == 5
                work = request(base, api)
                assert work['mode'] == 'legacy'
                # stale revision rejected
                request(base, api + '/rosters/clear', {'revision': 4, 'direction': 'b'}, 409)
                print('ALL REVIEW HTTP CHECKS PASSED')
            finally:
                server.shutdown(); t.join()


if __name__ == '__main__':
    main()
