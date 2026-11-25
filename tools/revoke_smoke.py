"""用真实 HTTP 工作流检查校验批次撤销对交接的影响。"""
import argparse
import csv
import io
import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from splice.codec import pack
from splice.db import Database
from splice.server import serve

FLOW = ('revoke', 'retrace', 'scope', 'handoff', 'concurrent')
SAMPLES = Path(__file__).resolve().parents[1] / 'examples'

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
            raise RuntimeError(f'{path} 预期 HTTP {status}，实际 {response.status}: {raw[:280]!r}')
        return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw


def sample(name):
    return json.loads((SAMPLES / f'{name}.json').read_text(encoding='utf-8'))


def labelled(trace, instrument, batch):
    return {**trace, 'instrument_id': instrument, 'calibration_batch': batch}


def check(base, through):
    api = '/api/splice/spans'
    steps = {name: index for index, name in enumerate(FLOW)}
    post = lambda path, obj, status=200: request(base, path, obj, status)
    get = lambda path: request(base, path)

    plan = sample('plan')
    a = labelled(sample('a'), 'OTDR-A', 'CB-2026-07')          # a, 批 07
    b = labelled(sample('b'), 'OTDR-B', 'CB-2026-07')          # b, 批 07
    repeat = labelled(sample('b-repeat'), 'OTDR-B', 'CB-2026-09')  # b, 批 09
    a_new = {**labelled(sample('a'), 'OTDR-A', 'CB-2026-09'), 'trace_id': 'A-106'}  # a, 批 09
    post(api, plan)
    for trace in (a, b, repeat, a_new):
        post(f'{api}/FX-W34/traces', trace)
    # 收件必须同时注明仪表与批次；缺一项被拒。
    partial = {'trace_id': 'A-999', 'direction': 'a', 'near_mm': 10000, 'far_mm': 1610000,
               'total_mdb': 850, 'instrument_id': 'OTDR-A',
               'events': sample('a')['events']}
    request(base, f'{api}/FX-W34/traces', partial, 422)
    assert post(f'{api}/FX-W34/selection', {'revision': 0, 'a': 'A-105', 'b': 'B-203'})['revision'] == 1
    assert post(f'{api}/FX-W34/releases', {'revision': 1})['digest']
    assert post(f'{api}/FX-W34/selection', {'revision': 1, 'a': 'A-106', 'b': 'B-203'})['revision'] == 2
    assert post(f'{api}/FX-W34/releases', {'revision': 2})['digest']

    other_plan = {**plan, 'span_id': 'FX-W35', 'label': '另一光段'}
    post(api, other_plan)
    x = labelled(sample('a'), 'OTDR-A', 'CB-2026-07')   # 另一光段的同仪表同批
    y = labelled(sample('b'), 'OTDR-B', 'CB-2026-07')   # 另一仪表的同号批次
    post(f'{api}/FX-W35/traces', x)
    post(f'{api}/FX-W35/traces', y)
    post(f'{api}/FX-W35/selection', {'revision': 0, 'a': 'A-105', 'b': 'B-203'})
    if steps[through] < steps['revoke']:
        return

    # 撤销 OTDR-A / CB-2026-07：只影响引用该乙端批次的已签件与在用修订。
    notice = post('/api/splice/revocations', {'instrument_id': 'OTDR-A', 'calibration_batch': 'CB-2026-07',
                                              'note': '计量室撤回该批证书'})
    assert notice['replayed'] is False
    assert notice['impacts']['releases'] == [
        {'span_id': 'FX-W34', 'revision': 1, 'digest': notice['impacts']['releases'][0]['digest'],
         'affected': [{'side': 'a', 'trace_id': 'A-105', 'instrument_id': 'OTDR-A',
                       'calibration_batch': 'CB-2026-07', 'source': 'stated'}],
         'notice_id': notice['notice_id']}]
    assert notice['impacts']['receipts'] == [
        {'span_id': 'FX-W34', 'trace_id': 'A-105', 'direction': 'a', 'adopted': False, 'notice_id': notice['notice_id']},
        {'span_id': 'FX-W35', 'trace_id': 'A-105', 'direction': 'a', 'adopted': True, 'notice_id': notice['notice_id']}]
    assert notice['impacts']['working'] == [
        {'span_id': 'FX-W35', 'revision': 1, 'side': 'a', 'trace_id': 'A-105', 'notice_id': notice['notice_id']}]
    assert post('/api/splice/revocations', {'instrument_id': 'OTDR-A', 'calibration_batch': 'CB-2026-07'})['replayed'] is True
    assert post('/api/splice/revocations', {'instrument_id': 'OTDR-A', 'calibration_batch': 'CB-2026-07',
                                            'notice_id': 'RV-OTHER'}, 409)['error']
    if steps[through] < steps['retrace']:
        return

    # 重传：仪表与批次两项须一致；原样重传复用，改任一项按新凭证处理或拒收。
    assert post(f'{api}/FX-W34/traces', a)['replayed'] is True
    assert post(f'{api}/FX-W34/traces', repeat)['replayed'] is True
    assert post(f'{api}/FX-W34/traces', {**repeat, 'instrument_id': 'OTDR-B'})['replayed'] is True
    request(base, f'{api}/FX-W34/traces', {**a, 'instrument_id': 'OTDR-Z'}, 409)
    request(base, f'{api}/FX-W34/traces', {**repeat, 'calibration_batch': 'CB-2026-07'}, 409)
    if steps[through] < steps['scope']:
        return

    # 同仪表同光段两个批次的签件只影响被撤销的那件。
    releases = get(f'{api}/FX-W34/releases')
    statuses = {item['revision']: item['handoff']['status'] for item in releases}
    assert statuses == {2: 'clear', 1: 'blocked'}
    rev1 = get(f'{api}/FX-W34/releases/1')
    assert rev1['handoff']['status'] == 'blocked'
    assert rev1['handoff']['affected'][0]['notice']['notice_id'] == notice['notice_id']
    assert rev1['snapshot']['budget']['status'] == 'ready'
    # 撤销不改冻结内容：旧快照仍记录原凭证与摘要。
    assert rev1['snapshot']['active']['a']['instrument_id'] == 'OTDR-A'
    from splice.codec import digest as sha_of, pack as freeze
    assert rev1['digest'] == sha_of(freeze(rev1['snapshot']))
    if steps[through] < steps['handoff']:
        return

    # 工作修订改用批 09，读数与合格结论不变，可继续签发与交接。
    assert post(f'{api}/FX-W34/releases', {'revision': 2}) == post(f'{api}/FX-W34/releases', {'revision': 2})
    # 另一光段仍采用被撤销批次：读数合格也须留置，并阻止新签。
    # 另一仪表的同号批次仍可交接：撤销按仪表+批次共同确定，不按批次单独生效。
    work = get(f'{api}/FX-W35')
    assert work['handoff']['status'] == 'blocked'
    assert work['handoff']['affected'][0]['side'] == 'a'
    assert work['handoff']['affected'][0]['instrument_id'] == 'OTDR-A'
    assert work['budget']['status'] == 'held' and 'revoked_calibration' in work['budget']['blockers']
    request(base, f'{api}/FX-W35/releases', {'revision': 1}, 409)
    # 换用被撤销批次的同号异仪表凭证：读数合格且可交接。
    assert post(f'{api}/FX-W35/selection', {'revision': 1, 'a': None, 'b': 'B-203'})['revision'] == 2
    assert get(f'{api}/FX-W35')['handoff']['status'] == 'clear'
    # 同光段同仪表仅换批次外的凭证后，该用另一批次才能解除留置。
    alt = labelled(sample('a'), 'OTDR-A', 'CB-2026-09')
    post(f'{api}/FX-W35/traces', {**alt, 'trace_id': 'A-107'})
    assert post(f'{api}/FX-W35/selection', {'revision': 2, 'a': 'A-107', 'b': 'B-203'})['revision'] == 3
    assert get(f'{api}/FX-W35')['handoff']['status'] == 'clear'
    # 未采用凭证仅列收件影响，不改变交接状态。
    post(f'{api}/FX-W35/traces', {**labelled(sample('a'), 'OTDR-A', 'CB-2026-07'), 'trace_id': 'A-OLD'})
    assert get(f'{api}/FX-W35')['handoff']['status'] == 'clear'
    unadopted = get('/api/splice/revocations')[0]['impacts']['receipts']
    assert {'span_id': 'FX-W35', 'trace_id': 'A-OLD', 'direction': 'a', 'adopted': False,
            'notice_id': notice['notice_id']} in unadopted
    if steps[through] < steps['concurrent']:
        return

    # 已签件保留原凭证、历史结论与按版导出，可追到撤销通知。
    archived = get(f'{api}/FX-W34/releases/1/evidence/A-105/A7')
    assert archived['notice']['notice_id'] == notice['notice_id']
    assert archived['event']['line'] == 1
    csv_rows = list(csv.DictReader(io.StringIO(get(f'{api}/FX-W34/releases/1/sites.csv').decode('utf-8'))))
    assert all(row['a_notice'] == notice['notice_id'] and row['handoff_status'] == 'blocked' for row in csv_rows)
    assert all(row['a_source'] == 'stated' and row['a_instrument'] == 'OTDR-A' and row['a_batch'] == 'CB-2026-07'
               for row in csv_rows)
    assert all(row['b_source'] == 'stated' and row['b_notice'] == '' for row in csv_rows)
    # 旧收件未注明来源：标为来源未注明并沿用原流程，不进入撤销范围。
    legacy = {**plan, 'span_id': 'FX-LEGACY', 'label': '旧资料光段'}
    post(api, legacy)
    old = {'trace_id': 'L-1', 'direction': 'a', 'near_mm': 10000, 'far_mm': 1610000,
           'total_mdb': 850, 'events': sample('a')['events']}
    received = post(f'{api}/FX-LEGACY/traces', old)
    assert received['source']['source'] == 'unstated'
    post(f'{api}/FX-LEGACY/selection', {'revision': 0, 'a': 'L-1', 'b': None})
    assert get(f'{api}/FX-LEGACY')['handoff']['status'] == 'clear'
    assert get(f'{api}/FX-LEGACY/traces')[0]['notice'] is None

    # 撤销与签发并发：先签的受影响件必须可追；撤销先生效则拒绝新签。
    race = {**plan, 'span_id': 'FX-RACE', 'label': '并发光段'}
    post(api, race)
    ra = labelled(sample('a'), 'OTDR-R', 'CAL-RACE')
    rb = labelled(sample('b'), 'OTDR-RB', 'CAL-RACE-SAFE')
    post(f'{api}/FX-RACE/traces', ra)
    post(f'{api}/FX-RACE/traces', rb)
    post(f'{api}/FX-RACE/selection', {'revision': 0, 'a': 'A-105', 'b': 'B-203'})
    gate = threading.Barrier(2)
    outcome = {}

    def issue_task():
        gate.wait()
        try:
            outcome['issue'] = post(f'{api}/FX-RACE/releases', {'revision': 1})
        except RuntimeError:
            outcome['issue'] = None

    def revoke_task():
        gate.wait()
        try:
            outcome['notice'] = post('/api/splice/revocations',
                                     {'instrument_id': 'OTDR-R', 'calibration_batch': 'CAL-RACE'})
        except RuntimeError:
            outcome['notice'] = None

    tasks = [threading.Thread(target=issue_task), threading.Thread(target=revoke_task)]
    for task in tasks:
        task.start()
    for task in tasks:
        task.join()
    assert outcome['notice'] is not None
    supports = get(f'{api}/FX-RACE/releases')
    marked = {item['revision']: item['handoff']['status'] for item in supports}
    if outcome['issue'] is not None:
        # 先签：签发件存在，但撤销后列为现时不可交接，并可追到撤销通知。
        assert marked == {1: 'blocked'}
        archived_race = get(f'{api}/FX-RACE/releases/1/evidence/A-105/A7')
        assert archived_race['notice']['notice_id'] == outcome['notice']['notice_id']
        assert outcome['notice']['impacts']['releases'][0]['revision'] == 1
    else:
        # 撤销先生效：没有新签件，撤销不留已签影响。
        assert marked == {}
        assert outcome['notice']['impacts']['releases'] == []
    return notice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', choices=FLOW, default=FLOW[-1])
    args = parser.parse_args()
    with TemporaryDirectory(prefix='splice-revoke-') as folder:
        database = Path(folder) / 'revoke.sqlite3'
        with serve(Database(database), 0) as server:
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                notice = check(f'http://127.0.0.1:{server.server_port}', args.through)
            finally:
                server.shutdown()
                thread.join()
        if notice:
            with Database(database).session() as connection:
                from splice.revocations import get_notice
                stored = get_notice(connection, notice['notice_id'])
                assert all(stored[key] == notice[key] for key in
                           ('notice_id', 'instrument_id', 'calibration_batch', 'note', 'revoked_at'))
    print(f'通过撤销工作流：{args.through}')


if __name__ == '__main__':
    main()
