"""跨版换版、拆并分组对账与版本扫测隔离的端到端验收。"""
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from splice.codec import pack
from splice.db import Database
from splice.server import serve

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'
FLOW = ('activate', 'isolation', 'issue', 'reconcile', 'reuse', 'retire-branch')


def sample(name):
    return json.loads((EXAMPLES / f'{name}.json').read_text(encoding='utf-8'))


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
            raise RuntimeError(f'{path} 预期 HTTP {status}，实际 {response.status}: {raw[:320]!r}')
        return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw


def group_by_identity(report, left_ids, right_ids):
    for group in report['groups']:
        left = [site['site_id'] for site in group['left_sites']]
        right = [site['site_id'] for site in group['right_sites']]
        if left == left_ids and right == right_ids:
            return group
    raise AssertionError(f'未找到对账组 {left_ids} -> {right_ids}')


def single_by_identity(report, side, ids):
    for group in report['single_side_groups']:
        sites = group['left_sites'] if side == 'left' else group['right_sites']
        if [site['site_id'] for site in sites] == ids and group['side'] == side:
            return group
    raise AssertionError(f'未找到单侧组 {side}:{ids}')


def check(base, through):
    steps = {name: index for index, name in enumerate(FLOW)}
    api = '/api/splice/spans'
    plan, a, b, repeat = [sample(name) for name in ('plan', 'a', 'b', 'b-repeat')]
    span_id = plan['span_id']
    span = f'{api}/{span_id}'
    write = lambda suffix, obj, status=200: request(base, span + suffix, obj, status)
    get = lambda suffix='': request(base, span + suffix)

    # 首版计划与两件双向扫测，先签发首版签件
    request(base, api, plan)
    for trace in (a, b, repeat):
        write('/traces', trace)
    write('/selection', {'revision': 0, 'a': a['trace_id'], 'b': b['trace_id']})
    first_release = write('/releases', {'revision': 1})
    first_revision = first_release['snapshot']['revision']
    assert first_revision == 1
    if steps[through] < steps['activate']:
        return

    # 启用第二版：拆分 J02，新增 J04；过期依据、漏项、冲突都必须拒绝且原计划照旧
    v2 = sample('v2-activation')
    activation = {'revision': 1, 'plan': v2['plan'], 'basis': v2['basis'], 'relations': v2['relations']}
    assert write('/versions', {**activation, 'revision': 99}, 409)['error']
    missing = dict(activation)
    missing['relations'] = [item for item in v2['relations'] if item['relation'] != 'added']
    assert write('/versions', missing, 422)['error']
    conflict = dict(activation)
    conflict['relations'] = [
        {'relation': 'continue', 'from_sites': ['J01'], 'to_sites': ['J01']},
        {'relation': 'split', 'from_sites': ['J02'], 'to_sites': ['J02A', 'J02B']},
        {'relation': 'continue', 'from_sites': ['J03'], 'to_sites': ['J03']},
        {'relation': 'added', 'from_sites': [], 'to_sites': ['J04']},
        {'relation': 'retired', 'from_sites': ['J03'], 'to_sites': []},
    ]
    assert write('/versions', conflict, 422)['error']
    stale_limit = dict(activation)
    stale_limit['plan'] = {**v2['plan'], 'sites': [
        site if site['site_id'] != 'J01' else {**site, 'limit_mdb': 159} for site in v2['plan']['sites']]}
    assert write('/versions', stale_limit, 422)['error']
    activated = write('/versions', activation)
    assert activated['plan_version'] == 2 and activated['parent_version'] == 1
    assert get('/versions')[-1]['basis'].startswith('北岸桥改线')
    relations = get('/versions/2/relations')
    assert [item['relation'] for item in relations] == ['continue', 'split', 'added']
    continued = next(item for item in relations if item['relation'] == 'continue')
    assert continued['from_sites'] == ['J01', 'J03'] and continued['to_sites'] == ['J01', 'J03']
    # 依据过期、漏项或冲突时原计划和采用照旧：工作修订只随成功启用推进到 2
    assert get()['revision'] == 2 and get()['plan']['sites'][1]['site_id'] == 'J02'
    if steps[through] < steps['isolation']:
        return

    # 新版仅用新版双向扫测：旧扫测迟到拒收，同编号同内容重传复用
    v2a, v2b = sample('v2-a'), sample('v2-b')
    assert write('/versions/2/traces', a, 409)['error']
    assert write('/versions/2/traces', v2a)['replayed'] is False
    assert write('/versions/2/traces', v2a)['replayed'] is True
    assert write('/versions/2/traces', {**v2a, 'total_mdb': 999}, 409)['error']
    write('/versions/2/traces', v2b)
    # 恢复原窗也拒用迟到旧扫测：旧版凭证在新版工作区不可见
    assert [item['trace_id'] for item in get('/versions/2/traces')] == ['A-V2-101', 'B-V2-201']
    assert request(base, f'{span}/versions/2/traces/A-105', status=404)['error']
    # 凭证方向与采用槽位不一致时拒绝
    assert write('/versions/2/selection',
                 {'revision': get()['revision'], 'a': v2b['trace_id'], 'b': None}, 422)['error']
    selection = write('/versions/2/selection',
                      {'revision': get()['revision'], 'a': v2a['trace_id'], 'b': v2b['trace_id']})
    v2_revision = selection['revision']
    work = get('/versions/2')
    assert work['plan_version'] == 2, work.get('plan_version')
    assert all(item['status'] == 'matched' for item in work['events']), \
        [(item['event_id'], item['status']) for item in work['events']]
    assert work['budget']['status'] == 'ready', work['budget']
    if steps[through] < steps['issue']:
        return

    v2_release = write('/versions/2/releases', {'revision': v2_revision})
    assert v2_release['digest'] == write('/versions/2/releases', {'revision': v2_revision})['digest']
    # 旧签件按原摘要读回，且冻结内容仍是首版 J02
    archived = get(f'/releases/{first_revision}')
    assert archived['digest'] == first_release['digest']
    assert [site['site_id'] for site in archived['snapshot']['sites']] == ['J01', 'J02', 'J03']
    if steps[through] < steps['reconcile']:
        return

    # 首版对拆分版：J01/J03 沿用成对，J02->J02A/J02B 拆分组；J04 单侧（新版新增）
    # 对账方向反向、缺失签件均拒绝
    assert request(base, f'{span}/reconcile/2/{v2_revision}/1/{first_revision}', status=422)['error']
    assert request(base, f'{span}/versions/2/releases/99', status=404)['error']
    split_report = get(f'/reconcile/1/{first_revision}/2/{v2_revision}')
    j02_group = group_by_identity(split_report, ['J02'], ['J02A', 'J02B'])
    assert j02_group['relations'] == ['split'] and j02_group['change_count'] == 1
    assert j02_group['left_loss_total_x2_mdb'] == 342
    assert j02_group['right_loss_total_x2_mdb'] == 270 and j02_group['delta_x2_mdb'] == -72
    j01_group = group_by_identity(split_report, ['J01'], ['J01'])
    assert j01_group['relations'] == ['continue']
    added_group = single_by_identity(split_report, 'right', ['J04'])
    assert added_group['left_sites'] == [] and added_group['right_loss_total_x2_mdb'] == 90
    assert not split_report['single_side_groups'] or all(group['side'] == 'right'
                                                          for group in split_report['single_side_groups'])

    # 启用第三版（两支再合并，中间第二版已签）；合并点 J02M
    v3 = sample('v3-activation')
    write('/versions', {'revision': get()['revision'], 'plan': v3['plan'], 'basis': v3['basis'],
                        'relations': v3['relations']})
    v3a, v3b = sample('v3-a'), sample('v3-b')
    write('/versions/3/traces', v3a)
    write('/versions/3/traces', v3b)
    revision = write('/versions/3/selection',
                     {'revision': get()['revision'], 'a': v3a['trace_id'], 'b': v3b['trace_id']})['revision']
    v3_work = get('/versions/3')
    assert v3_work['budget']['status'] == 'ready'
    v3_revision = write('/versions/3/releases', {'revision': revision})['snapshot']['revision']

    # 首末对账的拆并组只计原 J02 与合并点，可追两次变更和两件观测
    end_report = get(f'/reconcile/1/{first_revision}/3/{v3_revision}')
    merge_chain = group_by_identity(end_report, ['J02'], ['J02M'])
    assert merge_chain['relations'] == ['merge', 'split']
    assert merge_chain['change_count'] == 2
    assert merge_chain['versions'] == [1, 2, 3]
    assert merge_chain['left_loss_total_x2_mdb'] == 342
    assert merge_chain['right_loss_total_x2_mdb'] == 270
    # 中间版 J02A/J02B 只作关系证据，不出现在首末两侧，同号也不自动对齐
    assert all(site['site_id'] not in ('J02A', 'J02B') for site in merge_chain['left_sites'])
    assert all(site['site_id'] not in ('J02A', 'J02B') for site in merge_chain['right_sites'])
    # J04 在中间出现、末版退役：首末都无该点，故不进入首末组，仅在关系链中可追
    assert all(site['site_id'] != 'J04'
               for group in end_report['groups'] + end_report['single_side_groups']
               for site in group['left_sites'] + group['right_sites'])
    # J01/J03 两版沿用；J05 末版新增单列
    assert group_by_identity(end_report, ['J01'], ['J01'])['relations'] == ['continue']
    assert single_by_identity(end_report, 'right', ['J05'])

    # 改选拆分版签件对末版：J02A/J02B -> J02M 为合并组，退役的 J04 单列（left），新增 J05 单列（right）
    mid_report = get(f'/reconcile/2/{v2_revision}/3/{v3_revision}')
    merge_group = group_by_identity(mid_report, ['J02A', 'J02B'], ['J02M'])
    assert merge_group['relations'] == ['merge'] and merge_group['change_count'] == 1
    assert merge_group['left_loss_total_x2_mdb'] == 270
    assert merge_group['right_loss_total_x2_mdb'] == 270 and merge_group['delta_x2_mdb'] == 0
    assert single_by_identity(mid_report, 'left', ['J04'])
    assert single_by_identity(mid_report, 'right', ['J05'])

    # 版本 CSV 与冻结快照一致并带版本号
    csv_rows = list(csv.DictReader(io.StringIO(
        get(f'/versions/3/releases/{v3_revision}/sites.csv').decode('utf-8'))))
    assert [row['site_id'] for row in csv_rows] == ['J01', 'J02M', 'J03', 'J05']
    assert all(row['plan_version'] == '3' and row['snapshot_sha256'] for row in csv_rows)
    if steps[through] < steps['reuse']:
        return

    # 无关新点复用 J02 后退役：独立光段，同号不自动对齐，复用的 J02 单列
    reuse_span = 'FX-W34R'
    reuse_plan = {**plan, 'span_id': reuse_span, 'label': '同号复用演示段'}
    request(base, api, reuse_plan)
    request(base, f'{api}/{reuse_span}/traces', a)
    request(base, f'{api}/{reuse_span}/traces', b)
    request(base, f'{api}/{reuse_span}/selection',
            {'revision': 0, 'a': a['trace_id'], 'b': b['trace_id']})
    r1 = request(base, f'{api}/{reuse_span}/releases', {'revision': 1})
    # 第二版：J02 退役（无关新点 J09 占用同号语义但编号不与旧点对齐），J01/J03 沿用并新增 J09
    reuse_activation = {
        'revision': 1,
        'plan': {**reuse_plan, 'label': '同号复用演示段（第二版）', 'sites': [
            plan['sites'][0], plan['sites'][2],
            {'site_id': 'J09', 'at_mm': 980000, 'window_mm': 8000, 'limit_mdb': 200}]},
        'basis': '无关工程改线，原 J02 退役，另立新点 J09',
        'relations': [
            {'relation': 'continue', 'from_sites': ['J01'], 'to_sites': ['J01']},
            {'relation': 'retired', 'from_sites': ['J02'], 'to_sites': []},
            {'relation': 'continue', 'from_sites': ['J03'], 'to_sites': ['J03']},
            {'relation': 'added', 'from_sites': [], 'to_sites': ['J09']},
        ],
    }
    request(base, f'{api}/{reuse_span}/versions', reuse_activation)
    # 新版扫测：三个点
    r2a = {**v2a, 'trace_id': 'A-R2', 'events': [
        item for item in v2a['events'] if item['event_id'] in ('VA1', 'VA4')] + [
        {'event_id': 'RA9', 'at_mm': 990000, 'loss_mdb': 120}]}
    r2b = {**v2b, 'trace_id': 'B-R2', 'events': [
        {'event_id': 'RB1', 'at_mm': 1261000, 'loss_mdb': 50},
        {'event_id': 'RB3', 'at_mm': 351000, 'loss_mdb': 150},
        {'event_id': 'RB9', 'at_mm': 641000, 'loss_mdb': 130}]}
    r2a['total_mdb'], r2b['total_mdb'] = 700, 720
    request(base, f'{api}/{reuse_span}/versions/2/traces', r2a)
    request(base, f'{api}/{reuse_span}/versions/2/traces', r2b)
    revision = request(base, f'{api}/{reuse_span}/versions/2/selection',
                       {'revision': 2, 'a': 'A-R2', 'b': 'B-R2'})['revision']
    r2_work = request(base, f'{api}/{reuse_span}/versions/2')
    assert r2_work['budget']['status'] == 'ready'
    r2 = request(base, f'{api}/{reuse_span}/versions/2/releases', {'revision': revision})
    reuse_report = request(base, f'{api}/{reuse_span}/reconcile/1/1/2/{r2["snapshot"]["revision"]}')
    # 复用编号场景：退役 J02 作为单侧组，绝不与任何新版点自动对齐
    retired = single_by_identity(reuse_report, 'left', ['J02'])
    assert retired['right_sites'] == [] and retired['left_loss_total_x2_mdb'] == 342
    assert single_by_identity(reuse_report, 'right', ['J09'])
    assert group_by_identity(reuse_report, ['J01'], ['J01'])
    if steps[through] < steps['retire-branch']:
        return

    # 末版一支延续、一支退役：与拆分版对账时延续支独立对账，退役支单列
    branch_span = 'FX-W34B'
    branch_plan = {**plan, 'span_id': branch_span, 'label': '分支持续演示段'}
    request(base, api, branch_plan)
    request(base, f'{api}/{branch_span}/traces', a)
    request(base, f'{api}/{branch_span}/traces', b)
    request(base, f'{api}/{branch_span}/selection',
            {'revision': 0, 'a': a['trace_id'], 'b': b['trace_id']})
    request(base, f'{api}/{branch_span}/releases', {'revision': 1})
    branch_base = f'{api}/{branch_span}'
    current = lambda: request(base, branch_base)['revision']
    branch_v2 = {
        'revision': current(),
        'plan': {**branch_plan, 'label': '分支持续演示段（拆分版）', 'sites': [
            branch_plan['sites'][0],
            {'site_id': 'J02A', 'at_mm': 700000, 'window_mm': 8000, 'limit_mdb': 120},
            {'site_id': 'J02B', 'at_mm': 900000, 'window_mm': 8000, 'limit_mdb': 120},
            branch_plan['sites'][2]]},
        'basis': '桥改线拆分两支',
        'relations': [
            {'relation': 'continue', 'from_sites': ['J01'], 'to_sites': ['J01']},
            {'relation': 'split', 'from_sites': ['J02'], 'to_sites': ['J02A', 'J02B']},
            {'relation': 'continue', 'from_sites': ['J03'], 'to_sites': ['J03']},
        ],
    }
    request(base, f'{branch_base}/versions', branch_v2)
    # 拆分版只保留 J02A 支：J02B 在末版退役，其余延续（末版一支延续、一支退役）
    branch_v3 = {
        'revision': current(),
        'plan': {**branch_plan, 'label': '分支持续演示段（一支退役）', 'sites': [
            branch_plan['sites'][0],
            {'site_id': 'J02A', 'at_mm': 700000, 'window_mm': 8000, 'limit_mdb': 120},
            branch_plan['sites'][2]]},
        'basis': 'J02B 支退役，J02A 支延续',
        'relations': [
            {'relation': 'continue', 'from_sites': ['J01'], 'to_sites': ['J01']},
            {'relation': 'continue', 'from_sites': ['J02A'], 'to_sites': ['J02A']},
            {'relation': 'retired', 'from_sites': ['J02B'], 'to_sites': []},
            {'relation': 'continue', 'from_sites': ['J03'], 'to_sites': ['J03']},
        ],
    }
    request(base, f'{branch_base}/versions', branch_v3)
    # 给拆分版（v2）签发一件，再给末版（v3）签发一件；分支段无 J04，剔除其事件
    branch_v2a = {**v2a, 'trace_id': 'A-BR2',
                  'events': [item for item in v2a['events'] if item['event_id'] in ('VA1', 'VA2', 'VA3', 'VA4')]}
    branch_v2b = {**v2b, 'trace_id': 'B-BR2',
                  'events': [item for item in v2b['events'] if item['event_id'] in ('VB1', 'VB2', 'VB3', 'VB4')]}
    for trace in (branch_v2a, branch_v2b):
        request(base, f'{branch_base}/versions/2/traces', trace)
    v2_sel = request(base, f'{branch_base}/versions/2/selection',
                     {'revision': current(), 'a': branch_v2a['trace_id'], 'b': branch_v2b['trace_id']})
    v2_rev = request(base, f'{branch_base}/versions/2/releases',
                     {'revision': v2_sel['revision']})['snapshot']['revision']
    v3a = {**sample('v3-a'), 'trace_id': 'A-B3', 'events': [
        item for item in sample('v3-a')['events'] if item['event_id'] in ('WA1', 'WA3')] + [
        {'event_id': 'BA2', 'at_mm': 710000, 'loss_mdb': 75}]}
    v3b = {**sample('v3-b'), 'trace_id': 'B-B3', 'events': [
        item for item in sample('v3-b')['events'] if item['event_id'] in ('WB1', 'WB3')] + [
        {'event_id': 'BB2', 'at_mm': 921000, 'loss_mdb': 65}]}
    v3a['total_mdb'], v3b['total_mdb'] = 680, 700
    request(base, f'{branch_base}/versions/3/traces', v3a)
    request(base, f'{branch_base}/versions/3/traces', v3b)
    revision = request(base, f'{branch_base}/versions/3/selection',
                       {'revision': current(), 'a': 'A-B3', 'b': 'B-B3'})['revision']
    branch_work = request(base, f'{api}/{branch_span}/versions/3')
    assert branch_work['budget']['status'] == 'ready'
    v3_rev = request(base, f'{api}/{branch_span}/versions/3/releases',
                     {'revision': revision})['snapshot']['revision']
    branch_report = request(base, f'{branch_base}/reconcile/2/{v2_rev}/3/{v3_rev}')
    # 延续支 J02A 独立成对对账，退役支 J02B 单列
    continued = group_by_identity(branch_report, ['J02A'], ['J02A'])
    assert continued['relations'] == ['continue']
    retired_branch = single_by_identity(branch_report, 'left', ['J02B'])
    assert retired_branch['right_sites'] == []
    assert group_by_identity(branch_report, ['J01'], ['J01'])
    assert group_by_identity(branch_report, ['J03'], ['J03'])


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', choices=FLOW, default=FLOW[-1])
    args = parser.parse_args()
    with TemporaryDirectory(prefix='splice-versions-') as folder:
        database = Path(folder) / 'versions.sqlite3'
        with serve(Database(database), 0) as server:
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                check(f'http://127.0.0.1:{server.server_port}', args.through)
            finally:
                server.shutdown()
                thread.join()
    print(f'通过跨版工作流：{args.through}')


if __name__ == '__main__':
    main()
