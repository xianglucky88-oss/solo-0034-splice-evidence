"""用内置演示样本检查真实 HTTP 工作流和 SQLite 读回。"""
import argparse
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from splice.codec import digest, pack
from splice.db import Database
from splice.server import serve

FLOW = ('plan', 'receipts', 'selection', 'alignment', 'matching', 'pairing', 'closure',
        'evidence', 'issue', 'compare', 'export')


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


def check(base, through):
    api = '/api/splice/spans'
    plan, a, b, repeat = [request(base, f'/examples/{name}.json') for name in ('plan', 'a', 'b', 'b-repeat')]
    span = f"{api}/{plan['span_id']}"
    get = lambda suffix='': request(base, span + suffix)
    write = lambda suffix, obj, status=200: request(base, span + suffix, obj, status)
    steps = {name: index for index, name in enumerate(FLOW)}

    assert b'canvas' in request(base, '/')
    assert request(base, api, plan)['revision'] == 0
    assert request(base, api, {**plan, 'fixed_mdb': 0}, 409)['error']
    assert get()['budget']['status'] == 'held'
    if steps[through] < steps['receipts']:
        return

    first_receipts = [write('/traces', trace) for trace in (a, b, repeat)]
    assert [item['replayed'] for item in first_receipts] == [False, False, False]
    assert write('/traces', b)['replayed'] is True
    # 同号同内容仅换写单位仍算重传（B-203 的 dB 写法换成 mdb）；首收写法可查
    cross_unit = {key: value for key, value in b.items() if key not in ('total_unit', 'total_db')}
    cross_unit.update({'total_unit': 'mdb', 'total_mdb': 905,
                       'events': [{'event_id': 'B2', 'at_mm': 350000, 'loss_unit': 'db', 'loss_db': 0.178},
                                  {'event_id': 'B5', 'at_mm': 811000, 'loss_unit': 'db', 'loss_db': 0.145},
                                  {'event_id': 'B8', 'at_mm': 1265000, 'loss_unit': 'db', 'loss_db': 0.12}]})
    assert write('/traces', cross_unit)['replayed'] is True
    assert write('/traces', repeat)['replayed'] is True
    first_writing = get('/traces/B-203')
    assert first_writing['writing']['total_unit'] == 'db'
    assert first_writing['trace']['total_mdb'] == 905
    assert write('/traces', {**b, 'total_db': 0.999}, 409)['error']
    # 改方向、标记、事件数值或行序均为冲突
    assert write('/traces', {**b, 'direction': 'a'}, 409)['error']
    assert write('/traces', {**b, 'near_mm': 21001}, 409)['error']
    reordered = {**b, 'events': list(reversed(b['events']))}
    assert write('/traces', reordered, 409)['error']
    changed_event = {**b, 'events': [{**b['events'][0], 'loss_unit': 'mdb', 'loss_mdb': 179},
                                     *b['events'][1:]]}
    assert write('/traces', changed_event, 409)['error']
    assert write('/traces', {**b, 'events': [{**b['events'][0], 'event_id': 'B2X'},
                                             *b['events'][1:]]}, 409)['error']
    # 无法落到半毫分贝网格的读数拒收
    fine_grain = {**b, 'trace_id': 'B-FINE', 'events': [
        {**b['events'][0], 'loss_unit': 'mdb', 'loss_mdb': 100.25}, *b['events'][1:]]}
    assert write('/traces', fine_grain, 422)['error']
    fine_db = {**b, 'trace_id': 'B-FINEDB',
               'events': [{**b['events'][0], 'loss_unit': 'db', 'loss_db': 0.0456}, *b['events'][1:]]}
    assert write('/traces', fine_db, 422)['error']
    assert len(get('/traces')) == 3 and get()['revision'] == 0
    if steps[through] < steps['selection']:
        return

    assert write('/selection', {'revision': 0, 'a': a['trace_id'], 'b': None})['revision'] == 1
    assert write('/releases', {'revision': 1}, 409)['error']
    assert write('/selection', {'revision': 1, 'a': b['trace_id'], 'b': None}, 422)['error']
    selection = {'revision': 1, 'a': a['trace_id'], 'b': b['trace_id']}
    assert write('/selection', selection)['revision'] == 2
    assert write('/selection', selection, 409)['error']
    assert write('/selection', {**selection, 'revision': 2})['revision'] == 2
    if steps[through] < steps['alignment']:
        return

    work = get()
    normalized = {row['event_id']: row['along_mm'] for row in work['events']}
    assert normalized['A7'] == {'numerator': 363000, 'denominator': 1}
    assert normalized['B2'] == {'numerator': 1271000, 'denominator': 1}
    if steps[through] < steps['matching']:
        return

    assert all(row['status'] == 'matched' for row in work['events'])
    assert [row['observations']['b']['event_id'] for row in work['sites']] == ['B8', 'B5', 'B2']
    limited = '/api/splice/spans/DEMO-GAPS'
    second_site = {**plan['sites'][1], 'at_mm': 366000}
    request(base, api, {**plan, 'span_id': 'DEMO-GAPS', 'sites': [plan['sites'][0], second_site, plan['sites'][2]]})
    exceptions = [{**a['events'][0]}, {'event_id': 'duplicate-j3', 'at_mm': 1282000, 'loss_unit': 'mdb', 'loss_mdb': 34},
                  a['events'][2], {'event_id': 'outside', 'at_mm': 9000, 'loss_unit': 'mdb', 'loss_mdb': 0},
                  {'event_id': 'unmapped', 'at_mm': 740000, 'loss_unit': 'mdb', 'loss_mdb': 20}]
    request(base, limited + '/traces', {**a, 'events': exceptions})
    request(base, limited + '/selection', {'revision': 0, 'a': a['trace_id'], 'b': None})
    assert [event['status'] for event in request(base, limited)['events']] == [
        'ambiguous', 'collision', 'collision', 'outside', 'unmapped']
    if steps[through] < steps['pairing']:
        return

    assert [row['mean_x2_mdb'] for row in work['sites']] == [90, 342, 260]
    assert all(row['status'] == 'pass' for row in work['sites'])
    if steps[through] < steps['closure']:
        return

    budget = work['budget']
    assert (budget['status'], budget['estimate_x2_mdb'], budget['measured_x2_mdb'], budget['residual_x2_mdb']) == (
        'ready', 1652, 1755, 103)
    delivery = work['delivery']
    assert delivery['status'] == 'ready'
    assert delivery['totals_mdb'] == {'a': 850, 'b': 905}
    assert [site['mean_x2_mdb'] for site in delivery['sites']] == [90, 342, 260]
    heavy = {**b, 'trace_id': 'B-HIGH', 'total_db': 1.4}
    write('/traces', heavy)
    assert write('/selection', {**selection, 'revision': 2, 'b': heavy['trace_id']})['revision'] == 3
    assert get()['budget']['blockers'] == ['closure_over_limit']
    assert write('/releases', {'revision': 3}, 409)['error']
    assert write('/selection', {**selection, 'revision': 3})['revision'] == 4
    if steps[through] < steps['evidence']:
        return

    evidence = get('/evidence/A-105/A7')
    assert evidence['event']['line'] == 1 and evidence['sites'][0]['site_id'] == 'J01'
    assert request(base, span + '/evidence/B-204/B3', status=404)['error']
    if steps[through] < steps['issue']:
        return

    first = write('/releases', {'revision': 4})
    assert first == write('/releases', {'revision': 4})
    assert first['digest'] == digest(pack(first['snapshot']))
    # 旧签件按原摘要查回
    by_digest = get(f'/releases/by-digest/{first["digest"]}')
    assert by_digest['revision'] == 4 and by_digest['digest'] == first['digest']
    assert by_digest['snapshot'] == first['snapshot']
    if steps[through] < steps['compare']:
        return

    assert write('/selection', {**selection, 'revision': 4, 'b': repeat['trace_id']})['revision'] == 5
    latest = write('/releases', {'revision': 5})
    comparison = get('/compare/4/5')
    assert [row['delta_x2_mdb'] for row in comparison['sites']] == [12, -14, -5]
    assert comparison['before']['residual_x2_mdb'] == 103 and comparison['after']['residual_x2_mdb'] == 115
    assert latest['digest'] != first['digest'] and get('/releases/4') == first
    assert get('/releases/4/evidence/B-203/B8')['event']['line'] == 3
    if steps[through] < steps['export']:
        return

    rows = list(csv.DictReader(io.StringIO(get('/releases/4/sites.csv').decode('utf-8'))))
    assert [(row['site_id'], row['mean_x2_mdb'], row['booked_mean_x2_mdb']) for row in rows] == [
        ('J01', '90', '90'), ('J02', '342', '342'), ('J03', '260', '260')]
    assert all(row['snapshot_sha256'] == first['digest'] and row['b_trace'] == 'B-203' for row in rows)
    ledger = list(csv.DictReader(io.StringIO(get('/releases/4/delivery.csv').decode('utf-8'))))
    site_rows = [row for row in ledger if row['scope'] == 'site']
    assert all(float(row['booked_mdb']).is_integer() for row in site_rows)
    assert [(row['direction'], row['site_id'], row['booked_mdb']) for row in site_rows][:2] == [
        ('甲端', 'J01', '-30'), ('甲端', 'J02', '197')]
    return first


def check_fractional_delivery(base):
    """两点限值 100：甲向 100.5/99.5、乙向 99.5/100.5，四笔交割均为 100。"""
    plan = {
        'span_id': 'FX-HALF', 'label': '半格取整段', 'a_label': '甲', 'b_label': '乙',
        'length_mm': 1000000, 'fixed_mdb': 0, 'link_limit_mdb': 1000, 'residual_limit_mdb': 1000,
        'sites': [
            {'site_id': 'H1', 'at_mm': 300000, 'window_mm': 50000, 'limit_mdb': 100},
            {'site_id': 'H2', 'at_mm': 700000, 'window_mm': 50000, 'limit_mdb': 100},
        ],
    }
    a_trace = {
        'trace_id': 'HA', 'direction': 'a', 'near_mm': 0, 'far_mm': 1000000,
        'total_unit': 'mdb', 'total_mdb': 200,
        'events': [
            {'event_id': 'AH1', 'at_mm': 300000, 'loss_unit': 'mdb', 'loss_mdb': 100.5},
            {'event_id': 'AH2', 'at_mm': 700000, 'loss_unit': 'db', 'loss_db': 0.0995},
        ],
    }
    b_trace = {
        'trace_id': 'HB', 'direction': 'b', 'near_mm': 0, 'far_mm': 1000000,
        'total_unit': 'db', 'total_db': 0.2,
        'events': [
            # 乙端轴镜像：仪表 700000 对应统一里程 300000（H1）
            {'event_id': 'BH1', 'at_mm': 700000, 'loss_unit': 'mdb', 'loss_mdb': 99.5},
            {'event_id': 'BH2', 'at_mm': 300000, 'loss_unit': 'mdb', 'loss_mdb': 100.5},
        ],
    }
    api = '/api/splice/spans/FX-HALF'
    request(base, '/api/splice/spans', plan)
    assert request(base, api + '/traces', a_trace)['replayed'] is False
    assert request(base, api + '/traces', b_trace)['replayed'] is False
    # 换单位重传：0.1005 dB 与 100.5 mdb 同内容
    a_db = {**a_trace, 'events': [
        {'event_id': 'AH1', 'at_mm': 300000, 'loss_unit': 'db', 'loss_db': 0.1005},
        a_trace['events'][1]]}
    assert request(base, api + '/traces', a_db)['replayed'] is True
    request(base, api + '/selection', {'revision': 0, 'a': 'HA', 'b': 'HB'})
    work = request(base, api)
    assert work['budget']['status'] == 'ready'
    delivery = work['delivery']
    assert delivery['status'] == 'ready'
    booked = {(site['site_id'], side): site['observations'][side]['booked_mdb']
              for site in delivery['sites'] for side in ('a', 'b')}
    assert booked == {('H1', 'a'): 100, ('H1', 'b'): 100, ('H2', 'a'): 100, ('H2', 'b'): 100}
    assert delivery['totals_mdb'] == {'a': 200, 'b': 200}
    release = request(base, api + '/releases', {'revision': 1})
    assert release['snapshot']['delivery']['sites'][0]['observations']['a']['original_mdb'] == 100.5
    ledger = list(csv.DictReader(io.StringIO(
        request(base, api + '/releases/1/delivery.csv').decode('utf-8'))))
    assert [row['booked_mdb'] for row in ledger if row['scope'] == 'site'] == ['100'] * 4

    # 仅首点的光段：原值合格但唯一交割明细过限值，应留置，不能签发
    single = {
        'span_id': 'FX-ONE', 'label': '单点留置段', 'a_label': '甲', 'b_label': '乙',
        'length_mm': 1000000, 'fixed_mdb': 0, 'link_limit_mdb': 1000, 'residual_limit_mdb': 0,
        'sites': [{'site_id': 'S1', 'at_mm': 500000, 'window_mm': 50000, 'limit_mdb': 100}],
    }
    one_a = {'trace_id': 'OA', 'direction': 'a', 'near_mm': 0, 'far_mm': 1000000,
             'total_unit': 'mdb', 'total_mdb': 100.5,
             'events': [{'event_id': 'OA1', 'at_mm': 500000, 'loss_unit': 'mdb', 'loss_mdb': 100.5}]}
    one_b = {'trace_id': 'OB', 'direction': 'b', 'near_mm': 0, 'far_mm': 1000000,
             'total_unit': 'mdb', 'total_mdb': 99.5,
             'events': [{'event_id': 'OB1', 'at_mm': 500000, 'loss_unit': 'mdb', 'loss_mdb': 99.5}]}
    request(base, '/api/splice/spans', single)
    request(base, '/api/splice/spans/FX-ONE/traces', one_a)
    request(base, '/api/splice/spans/FX-ONE/traces', one_b)
    request(base, '/api/splice/spans/FX-ONE/selection', {'revision': 0, 'a': 'OA', 'b': 'OB'})
    held = request(base, '/api/splice/spans/FX-ONE')
    assert held['budget']['status'] == 'ready'
    assert held['delivery']['status'] == 'held'
    assert 'delivery_site_over_limit' in held['delivery']['blockers']
    assert request(base, '/api/splice/spans/FX-ONE/releases', {'revision': 1}, 409)['error']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', choices=FLOW, default=FLOW[-1])
    args = parser.parse_args()
    with TemporaryDirectory(prefix='splice-demo-') as folder:
        database = Path(folder) / 'example.sqlite3'
        with serve(Database(database), 0) as server:
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                frozen = check(f'http://127.0.0.1:{server.server_port}', args.through)
                if args.through == FLOW[-1]:
                    check_fractional_delivery(f'http://127.0.0.1:{server.server_port}')
            finally:
                server.shutdown()
                thread.join()
        if frozen:
            with Database(database).session() as connection:
                from splice.releases import get_release
                assert get_release(connection, 'FX-W34', 4) == frozen
    print(f'通过演示工作流：{args.through}')


if __name__ == '__main__':
    main()
