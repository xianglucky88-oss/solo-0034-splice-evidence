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
        'evidence', 'issue', 'compare', 'export', 'route')


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
    if steps[through] < steps['route']:
        return first, None

    route = check_route(base, request, first)
    return first, route


def check_route(base, request, first):
    api = '/api/splice/spans'
    plan, a_trace, b_trace = [request(base, f'/examples/{name}.json') for name in ('w35', 'w35-a', 'w35-b')]
    request(base, api, plan)
    second = f"{api}/{plan['span_id']}"
    request(base, second + '/traces', a_trace)
    request(base, second + '/traces', b_trace)
    assert request(base, second + '/selection', {'revision': 0, 'a': a_trace['trace_id'], 'b': b_trace['trace_id']})['revision'] == 1
    signed = request(base, second + '/releases', {'revision': 1})
    assert signed['snapshot']['budget']['status'] == 'ready'

    route = request(base, '/examples/route.json')
    route['segments'][0]['revision'] = 4
    routes = '/api/splice/routes'
    assert request(base, routes, route)['plan']['route_id'] == route['route_id']
    assert request(base, routes, {**route, 'residual_limit_mdb': 1}, 409)['error']
    path = f"{routes}/{route['route_id']}"
    work = request(base, path)
    assert [item['span_id'] for item in work['segments']] == ['FX-W34', 'FX-W35']
    assert [item['order'] for item in work['segments']] == [1, 2]
    assert work['segments'][0]['release_digest'] == first['digest']
    assert work['segments'][1]['start_mm'] == 1_601_500
    assert work['bridges'][0]['record_count'] == 2
    assert work['bridges'][0]['order'] == 1
    assert work['budget']['measured_a_mdb'] == 1208 and work['budget']['measured_b_mdb'] == 1280
    assert work['budget']['measured_x2_mdb'] == 2488
    assert work['budget']['estimate_x2_mdb'] == 2384
    assert work['budget']['residual_x2_mdb'] == 104
    assert work['budget']['status'] == 'ready'

    handed = request(base, path + '/releases', {})
    assert handed == request(base, path + '/releases', {})
    assert handed['digest'] == digest(pack(handed['snapshot']))
    assert request(base, path + '/releases/' + handed['digest']) == handed
    assert request(base, path + '/releases/' + '0' * 64, status=404)['error']
    parts = list(csv.DictReader(io.StringIO(
        request(base, path + f"/releases/{handed['digest']}/parts.csv").decode('utf-8'))))
    assert [(row['part'], row['ref']) for row in parts] == [
        ('segment', 'FX-W34'), ('segment', 'FX-W35'), ('bridge', '河西接续箱/端口1>河西接续箱/端口2'),
        ('total', '')]

    broken = {**route, 'route_id': 'FX-R1-BROKEN', 'bridges': []}
    request(base, routes, broken)
    assert request(base, routes + '/FX-R1-BROKEN')['budget']['blockers'] == ['missing_bridge']
    assert request(base, routes + '/FX-R1-BROKEN/releases', {}, 409)['error']

    reverse = {**route, 'route_id': 'FX-R1-REV', 'start': route['end'], 'end': route['start'],
               'segments': [
                   {'span_id': 'FX-W35', 'revision': 1, 'entry': route['end'],
                    'exit': {'box': '河西接续箱', 'port': '端口2'}, 'orientation': 'reverse'},
                   {'span_id': 'FX-W34', 'revision': 4, 'entry': {'box': '河西接续箱', 'port': '端口1'},
                    'exit': route['start'], 'orientation': 'reverse'}],
               'bridges': [route['bridges'][0]]}
    request(base, routes, reverse)
    mirrored = request(base, routes + '/FX-R1-REV')
    assert [item['span_id'] for item in mirrored['segments']] == ['FX-W35', 'FX-W34']
    assert mirrored['budget']['measured_a_mdb'] == work['budget']['measured_b_mdb']
    assert mirrored['budget']['measured_b_mdb'] == work['budget']['measured_a_mdb']
    assert mirrored['budget']['estimate_x2_mdb'] == work['budget']['estimate_x2_mdb']
    assert mirrored['budget']['residual_x2_mdb'] == work['budget']['residual_x2_mdb']
    assert [item['site_id'] for item in mirrored['sites']] == ['J04', 'J03', 'J02', 'J01']
    assert mirrored['sites'][0]['at_mm'] == 500_000
    assert mirrored['sites'][-1]['at_mm'] == 2_041_500
    assert mirrored['sites'][-1]['observations']['a']['source_side'] == 'b'
    assert mirrored['bridges'][0]['reversed'] is True
    assert mirrored['bridges'][0]['forward_mdb'] == route['bridges'][0]['backward_mdb']

    for route_id, change, expected in (
            ('FX-R1-LINK-OK', {'link_limit_mdb': 1244}, []),
            ('FX-R1-LINK-BAD', {'link_limit_mdb': 1243}, ['link_over_limit']),
            ('FX-R1-CLOSE-OK', {'residual_limit_mdb': 52}, []),
            ('FX-R1-CLOSE-BAD', {'residual_limit_mdb': 51}, ['closure_over_limit'])):
        request(base, routes, {**route, 'route_id': route_id, **change})
        assert request(base, routes + '/' + route_id)['budget']['blockers'] == expected
    return handed


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
                from splice.routes import get_route_release
                span_release, route_release = frozen
                assert get_release(connection, 'FX-W34', 4) == span_release
                if route_release:
                    assert get_route_release(connection, 'FX-R1', route_release['digest']) == route_release
    print(f'通过演示工作流：{args.through}')


if __name__ == '__main__':
    main()
