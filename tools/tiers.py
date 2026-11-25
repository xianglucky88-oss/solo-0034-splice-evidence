"""限值档登记、按实测日期选档与跨档复核的 HTTP 工作流检查。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from splice.codec import pack
from splice.db import Database
from splice.server import serve

API = '/api/splice/spans'


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


def tier(tier_id, start, end, *, site_limits, link, residual, label=None):
    return {'tier_id': tier_id, 'label': label or tier_id, 'start_on': start, 'end_on': end,
            'site_limits': [{'site_id': site, 'limit_mdb': limit} for site, limit in site_limits.items()],
            'link_limit_mdb': link, 'residual_limit_mdb': residual}


def check_rejudge(base):
    """前后闭合差 0.080 / 0.039 dB，原限值 0.080 / 0.040 dB：用后件档复核只应因闭合暂缓前件。"""
    plan = {'span_id': 'FX-CLOSE', 'label': '闭合复核段', 'a_label': '甲', 'b_label': '乙',
            'length_mm': 1000000, 'fixed_mdb': 0, 'link_limit_mdb': 1000, 'residual_limit_mdb': 160,
            'sites': [{'site_id': 'J01', 'at_mm': 500000, 'window_mm': 10000, 'limit_mdb': 100}]}
    request(base, API, plan)
    span = f'{API}/FX-CLOSE'
    get = lambda suffix='': request(base, span + suffix)
    write = lambda suffix, obj, status=200: request(base, span + suffix, obj, status)
    write('/limits', {'tiers': [
        tier('OLD', '2026-01-01', '2026-07-01', site_limits={'J01': 100}, link=1000, residual=80),
        tier('NEW', '2026-07-01', '2027-01-01', site_limits={'J01': 100}, link=1000, residual=40)]})
    traces = {
        'A1': {'trace_id': 'A1', 'direction': 'a', 'near_mm': 0, 'far_mm': 1000000, 'total_mdb': 80,
               'events': [{'event_id': 'a1', 'at_mm': 500000, 'loss_mdb': 0}]},
        'B1': {'trace_id': 'B1', 'direction': 'b', 'near_mm': 0, 'far_mm': 1000000, 'total_mdb': 80,
               'events': [{'event_id': 'b1', 'at_mm': 500000, 'loss_mdb': 0}]},
        'A2': {'trace_id': 'A2', 'direction': 'a', 'near_mm': 0, 'far_mm': 1000000, 'total_mdb': 40,
               'events': [{'event_id': 'a2', 'at_mm': 500000, 'loss_mdb': 0}]},
        'B2': {'trace_id': 'B2', 'direction': 'b', 'near_mm': 0, 'far_mm': 1000000, 'total_mdb': 38,
               'events': [{'event_id': 'b2', 'at_mm': 500000, 'loss_mdb': 0}]},
    }
    for record in traces.values():
        write('/traces', record)
    for name, when in (('A1', '2026-02-01'), ('B1', '2026-02-02')):
        write(f'/traces/{name}/measured_on', {'measured_on': when})
    write('/selection', {'revision': 0, 'a': 'A1', 'b': 'B1'})
    assert get()['tier']['tier_id'] == 'OLD' and get()['budget']['status'] == 'ready'
    before = write('/releases', {'revision': get()['revision'], 'archive': get()['tier']['stamp']})
    assert before['snapshot']['budget']['residual_x2_mdb'] == 160
    assert before['snapshot']['budget']['residual_limit_mdb'] == 80

    write(f'/traces/A2/measured_on', {'measured_on': '2026-08-01'})
    write(f'/traces/B2/measured_on', {'measured_on': '2026-08-02'})
    write('/selection', {'revision': get()['revision'], 'a': 'A2', 'b': 'B2'})
    assert get()['tier']['tier_id'] == 'NEW' and get()['budget']['status'] == 'ready'
    # 签发须对应操作员看过的档案版本：档案被更订后，旧版本号不能签发。
    seen = get()['tier']['stamp']
    write(f'/traces/B2/measured_on', {'measured_on': '2026-08-04'})
    assert write('/releases', {'revision': get()['revision'], 'archive': seen}, 409)['error']
    write(f'/traces/B2/measured_on', {'measured_on': '2026-08-02'})
    after = write('/releases', {'revision': get()['revision'], 'archive': get()['tier']['stamp']})
    assert after['snapshot']['budget']['residual_x2_mdb'] == 78
    assert after['snapshot']['budget']['residual_limit_mdb'] == 40

    version = after['snapshot']['tier']['registry_version']
    result = get(f'/compare/{before["snapshot"]["revision"]}/{after["snapshot"]["revision"]}'
                 f'?archive={version}&tier=NEW')['rejudge']
    assert result['before']['original']['status'] == 'ready'
    assert result['before']['judgment']['blockers'] == ['closure_over_limit']
    assert result['before']['judgment']['status'] == 'held'
    assert result['after']['judgment']['status'] == 'ready'
    assert result['before']['tier']['tier_id'] == 'OLD' and result['after']['tier']['tier_id'] == 'NEW'

    # 只能按原件实际采用的同范围档位重判；不存在的登记版本或档位组合拒绝。
    request(base, f'{span}/compare/{before["snapshot"]["revision"]}/{after["snapshot"]["revision"]}'
                  f'?archive=999&tier=OLD', status=422)
    request(base, f'{span}/compare/{before["snapshot"]["revision"]}/{after["snapshot"]["revision"]}'
                  f'?tier=NEW', status=400)
    # 重判不改动已冻结的签件。
    assert get(f'/releases/{before["snapshot"]["revision"]}')['digest'] == before['digest']


def check(base):
    plan = json.loads((Path(__file__).resolve().parents[1] / 'examples/plan.json').read_text(encoding='utf-8'))
    a = json.loads((Path(__file__).resolve().parents[1] / 'examples/a.json').read_text(encoding='utf-8'))
    b = json.loads((Path(__file__).resolve().parents[1] / 'examples/b.json').read_text(encoding='utf-8'))
    repeat = json.loads((Path(__file__).resolve().parents[1] / 'examples/b-repeat.json').read_text(encoding='utf-8'))
    request(base, API, plan)
    span = f'{API}/{plan["span_id"]}'
    get = lambda suffix='': request(base, span + suffix)
    write = lambda suffix, obj, status=200: request(base, span + suffix, obj, status)

    # 未启用限值档的光段照旧：按计划限值判定，不因缺日期留置。
    assert get()['tier']['status'] == 'disabled' and get()['budget']['status'] == 'held'
    for trace in (a, b, repeat):
        write('/traces', trace)
    write('/selection', {'revision': 0, 'a': a['trace_id'], 'b': b['trace_id']})
    assert get()['tier']['status'] == 'disabled'
    assert get()['budget']['blockers'] == []

    # 登记两个档：年初档较宽，年中档收紧 J01 限值。
    loose = tier('T-2026H1', '2026-01-01', '2026-07-01',
                 site_limits={'J01': 160, 'J02': 200, 'J03': 180}, link=1260, residual=80)
    tight = tier('T-2026H2', '2026-07-01', '2027-01-01',
                 site_limits={'J01': 60, 'J02': 200, 'J03': 180}, link=1260, residual=60)
    saved = write('/limits', {'tiers': [loose, tight]})
    assert saved['version'] == 1 and saved['archive']['stamp'] == 1

    # 缺日期：按方向报告缺哪一向。
    described = get()['tier']
    assert described['status'] == 'unresolved'
    assert {item['direction'] for item in described['problems']} == {'a', 'b'}
    assert all(item['code'] == 'missing_date' for item in described['problems'])
    assert 'tier_unresolved' in get()['budget']['blockers']

    # 两端日期落在同一档才可选；起日含、止日不含。
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-02-10'})
    write(f'/traces/{b["trace_id"]}/measured_on', {'measured_on': '2026-03-09'})
    assert get()['tier']['tier_id'] == 'T-2026H1'
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-07-01'})
    write(f'/traces/{b["trace_id"]}/measured_on', {'measured_on': '2026-07-01'})
    assert get()['tier']['tier_id'] == 'T-2026H2'
    assert get()['budget']['residual_limit_mdb'] == 60

    # 跨档：两端各自命中不同档，两个方向都说明。
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-06-30'})
    crossed = get()['tier']
    assert crossed['status'] == 'unresolved'
    assert {item['direction'] for item in crossed['problems']} == {'a', 'b'}
    assert all(item['code'] == 'cross_tier' for item in crossed['problems'])

    # 空档：日期落在档位之间的缝隙里。
    write('/limits', {'tiers': [loose, {**tight, 'start_on': '2026-08-01', 'end_on': '2027-01-01'}]})
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-07-15'})
    write(f'/traces/{b["trace_id"]}/measured_on', {'measured_on': '2026-08-05'})
    gap = get()['tier']
    assert gap['status'] == 'unresolved'
    assert [item['code'] for item in gap['problems']] == ['no_tier']
    assert gap['problems'][0]['direction'] == 'a'

    # 重叠：再登记一版互相盖住的档位，两端日期都被多处命中。
    write('/limits', {'tiers': [loose, {**loose, 'tier_id': 'T-OVER', 'start_on': '2026-03-01'}]})
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-04-01'})
    write(f'/traces/{b["trace_id"]}/measured_on', {'measured_on': '2026-04-02'})
    overlap = get()['tier']
    assert overlap['status'] == 'unresolved'
    assert all(item['code'] == 'overlap' for item in overlap['problems'])

    # 回到干净的两档，签发前后两件。
    write('/limits', {'tiers': [loose, tight]})
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-02-10'})
    write(f'/traces/{b["trace_id"]}/measured_on', {'measured_on': '2026-03-09'})
    assert get()['tier']['tier_id'] == 'T-2026H1'
    first = write('/releases', {'revision': get()['revision'], 'archive': get()['tier']['stamp']})
    assert first['snapshot']['tier']['tier_id'] == 'T-2026H1'
    write('/selection', {'revision': get()['revision'], 'a': a['trace_id'], 'b': repeat['trace_id']})
    write(f'/traces/{repeat["trace_id"]}/measured_on', {'measured_on': '2026-08-05'})
    write(f'/traces/{a["trace_id"]}/measured_on', {'measured_on': '2026-08-01'})
    assert get()['tier']['tier_id'] == 'T-2026H2'
    second = write('/releases', {'revision': get()['revision'], 'archive': get()['tier']['stamp']})
    assert second['snapshot']['tier']['tier_id'] == 'T-2026H2'

    # 旧件仍按当时档案查回：第一件的档位登记版本不随后续登记漂移。
    archived = get(f'/releases/{first["snapshot"]["revision"]}')['snapshot']
    assert archived['tier']['registry_version'] == first['snapshot']['tier']['registry_version']
    assert archived['tier']['tier_id'] == 'T-2026H1'
    assert get('/limits/4')['tiers'][0]['tier_id'] == 'T-2026H1'

    # 比较不同档的两件：分列测量与核算变化、限值变化。
    compared = get(f'/compare/{first["snapshot"]["revision"]}/{second["snapshot"]["revision"]}')
    assert [row['site_id'] for row in compared['measurement']['sites']] == ['J01', 'J02', 'J03']
    limits = {row['site_id']: (row['before_mdb'], row['after_mdb']) for row in compared['limits']['sites']}
    assert limits['J01'] == (160, 60)
    assert compared['limits']['residual'] == {'before_mdb': 80, 'after_mdb': 60}
    assert compared['accounting']['residual_before_mdb'] != compared['accounting']['residual_after_mdb']

    # 用任一原件实际采用的同范围档重判两件，保留原结论及来源。
    first_version = first['snapshot']['tier']['registry_version']
    second_version = second['snapshot']['tier']['registry_version']
    options = {(item['registry_version'], item['tier_id']) for item in compared['rejudge_options']}
    assert options == {(first_version, 'T-2026H1'), (second_version, 'T-2026H2')}
    rejudged = get(f'/compare/{first["snapshot"]["revision"]}/{second["snapshot"]["revision"]}'
                   f'?archive={second_version}&tier=T-2026H2')
    assert rejudged['rejudge']['tier_id'] == 'T-2026H2'
    for side in ('before', 'after'):
        part = rejudged['rejudge'][side]
        assert part['original'] and part['judgment'] and part['digest']
        assert part['judgment']['tier_id'] == 'T-2026H2'

    return first, second


def main():
    with TemporaryDirectory(prefix='splice-tiers-') as folder:
        with serve(Database(Path(folder) / 'tiers.sqlite3'), 0) as server:
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                check(f'http://127.0.0.1:{server.server_port}')
                check_rejudge(f'http://127.0.0.1:{server.server_port}')
            finally:
                server.shutdown()
                thread.join()
    print('通过限值档工作流')


if __name__ == '__main__':
    main()
