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

    for trace in (a, b, repeat):
        assert write('/traces', trace)['replayed'] is False
    assert write('/traces', b)['replayed'] is True
    assert write('/traces', {**b, 'total_mdb': 999}, 409)['error']
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
    exceptions = [{**a['events'][0]}, {'event_id': 'duplicate-j3', 'at_mm': 1282000, 'loss_mdb': 34},
                  a['events'][2], {'event_id': 'outside', 'at_mm': 9000, 'loss_mdb': 0},
                  {'event_id': 'unmapped', 'at_mm': 740000, 'loss_mdb': 20}]
    request(base, limited + '/traces', {**a, 'events': exceptions})
    request(base, limited + '/selection', {'revision': 0, 'a': a['trace_id'], 'b': None})
    limited_events = request(base, limited)['events']
    assert [event['status'] for event in limited_events] == [
        'undetermined', 'contested', 'contested', 'outside', 'unmapped']
    assert limited_events[0]['basis'] == 'overlap'
    assert limited_events[1]['basis'] == limited_events[2]['basis'] == 'same_end'

    def narrow(span_id, sites, events):
        request(base, api, {**plan, 'span_id': span_id, 'sites': sites})
        request(base, f'{api}/{span_id}/traces', {**a, 'events': events})
        request(base, f'{api}/{span_id}/selection', {'revision': 0, 'a': a['trace_id'], 'b': None})
        return request(base, f'{api}/{span_id}')['events']

    pair = [{'site_id': 'K1', 'at_mm': 500000, 'window_mm': 100000, 'limit_mdb': 100},
            {'site_id': 'K2', 'at_mm': 600000, 'window_mm': 100000, 'limit_mdb': 100}]
    # Two distinct mileages inside the shared window still pair in mileage order,
    # while a lone event that fits both sites has no determined ownership.
    layering = narrow('DEMO-LAYER', pair, [
        {'event_id': 'S1', 'at_mm': 520000, 'loss_mdb': 0},
        {'event_id': 'S2', 'at_mm': 580000, 'loss_mdb': 0}])
    assert [(event['status'], event.get('site_id')) for event in layering] == [
        ('matched', 'K1'), ('matched', 'K2')]
    assert [(row['observations']['a']['event_id'], row['site_id']) for row in
            request(base, f'{api}/DEMO-LAYER')['sites']] == [('S1', 'K1'), ('S2', 'K2')]
    sole = narrow('DEMO-SOLE', pair, [{'event_id': 'S1', 'at_mm': 550000, 'loss_mdb': 0}])
    assert [(event['status'], event['basis']) for event in sole] == [('undetermined', 'overlap')]
    costly = narrow('DEMO-COST', pair, [
        {'event_id': 'S1', 'at_mm': 480000, 'loss_mdb': 0},
        {'event_id': 'S2', 'at_mm': 550000, 'loss_mdb': 0},
        {'event_id': 'S3', 'at_mm': 650000, 'loss_mdb': 0}])
    assert [(event['status'], event['basis']) for event in costly] == [
        ('contested', 'competing')] * 3

    # A 100 m span whose plan marks 50 m field: both scans read 0 and 100, while
    # the 50 m mark reads 60 m from A and 40 m from B.  The 50 m reading lands in
    # the 48–52 m window and the 55 m reading in the 50–58 m window; only the
    # maximum pairing can tell the two marked events apart.
    marked = {**plan, 'span_id': 'DEMO-MARKS', 'length_mm': 100000, 'marks_mm': [50000],
              'sites': [{'site_id': 'M1', 'at_mm': 50000, 'window_mm': 2000, 'limit_mdb': 100},
                        {'site_id': 'M2', 'at_mm': 54000, 'window_mm': 4000, 'limit_mdb': 100}]}
    request(base, api, marked)
    marked_a = {'trace_id': 'MA', 'direction': 'a', 'near_mm': 0, 'far_mm': 100000, 'total_mdb': 100,
                'marks_mm': [60000], 'events': [{'event_id': 'MA1', 'at_mm': 60000, 'loss_mdb': 10},
                                                {'event_id': 'MA2', 'at_mm': 64000, 'loss_mdb': 10}]}
    marked_b = {'trace_id': 'MB', 'direction': 'b', 'near_mm': 0, 'far_mm': 100000, 'total_mdb': 100,
                'marks_mm': [40000], 'events': [{'event_id': 'MB1', 'at_mm': 40000, 'loss_mdb': 10},
                                                {'event_id': 'MB2', 'at_mm': 36000, 'loss_mdb': 10}]}
    for trace in (marked_a, marked_b):
        request(base, f'{api}/DEMO-MARKS/traces', trace)
    request(base, f'{api}/DEMO-MARKS/selection', {'revision': 0, 'a': 'MA', 'b': 'MB'})
    marked_work = request(base, f'{api}/DEMO-MARKS')
    assert {row['event_id']: row['along_mm'] for row in marked_work['events']} == {
        'MA1': {'numerator': 50000, 'denominator': 1}, 'MA2': {'numerator': 55000, 'denominator': 1},
        'MB1': {'numerator': 50000, 'denominator': 1}, 'MB2': {'numerator': 55000, 'denominator': 1}}
    assert all(entry['status'] == 'ok' for entry in marked_work['calibrations'])
    assert [row['mean_x2_mdb'] for row in marked_work['sites']] == [20, 20]
    assert [row['observations']['a']['event_id'] for row in marked_work['sites']] == ['MA1', 'MA2']
    assert [row['observations']['b']['event_id'] for row in marked_work['sites']] == ['MB1', 'MB2']

    # B read the marks in the wrong order: the whole direction is held.
    ordered = {**plan, 'span_id': 'DEMO-ORDER', 'length_mm': 100000, 'marks_mm': [30000, 70000],
               'sites': [{'site_id': 'N1', 'at_mm': 50000, 'window_mm': 5000, 'limit_mdb': 100}]}
    request(base, api, ordered)
    request(base, f'{api}/DEMO-ORDER/traces',
            {'trace_id': 'OE', 'direction': 'a', 'near_mm': 0, 'far_mm': 100000, 'total_mdb': 100,
             'marks_mm': [60000, 40000], 'events': [{'event_id': 'OE1', 'at_mm': 50000, 'loss_mdb': 10}]})
    request(base, f'{api}/DEMO-ORDER/selection', {'revision': 0, 'a': 'OE', 'b': None})
    order_work = request(base, f'{api}/DEMO-ORDER')
    assert order_work['calibrations'][0]['reason'] == 'mark_order'
    assert order_work['events'][0]['status'] == 'held'
    assert 'calibration_held' in order_work['budget']['blockers']
    # Reporting fewer marks than the plan requires also holds the direction.
    request(base, f'{api}/DEMO-ORDER/traces',
            {'trace_id': 'OE-MISS', 'direction': 'a', 'near_mm': 0, 'far_mm': 100000, 'total_mdb': 100,
             'marks_mm': [60000], 'events': [{'event_id': 'OE1', 'at_mm': 50000, 'loss_mdb': 10}]})
    request(base, f'{api}/DEMO-ORDER/selection', {'revision': 1, 'a': 'OE-MISS', 'b': None})
    missing_work = request(base, f'{api}/DEMO-ORDER')
    assert missing_work['calibrations'][0]['reason'] == 'mark_count'
    assert missing_work['events'][0]['status'] == 'held'
    evidence = request(base, f'{api}/DEMO-MARKS/evidence/MA/MA1')
    assert evidence['calibration']['status'] == 'ok' and evidence['calibration']['marks'][1]['at_mm'] == {
        'numerator': 50000, 'denominator': 1}
    assert [site['site_id'] for site in evidence['sites']] == ['M1', 'M2']
    if steps[through] < steps['pairing']:
        return

    assert [row['mean_x2_mdb'] for row in work['sites']] == [90, 342, 260]
    assert all(row['status'] == 'pass' for row in work['sites'])
    if steps[through] < steps['closure']:
        return

    budget = work['budget']
    assert (budget['status'], budget['estimate_x2_mdb'], budget['measured_x2_mdb'], budget['residual_x2_mdb']) == (
        'ready', 1652, 1755, 103)
    heavy = {**b, 'trace_id': 'B-HIGH', 'total_mdb': 1400}
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
    assert [(row['site_id'], row['mean_x2_mdb']) for row in rows] == [('J01', '90'), ('J02', '342'), ('J03', '260')]
    assert all(row['snapshot_sha256'] == first['digest'] and row['b_trace'] == 'B-203' for row in rows)
    return first


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
