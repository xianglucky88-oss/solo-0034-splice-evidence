"""限值档登记：按起止日划分验收口径，起日含、止日不含。

档位登记后不修改。再次登记会把整组档位作为一个新版本追加，旧版本保留，供旧签件按当时所用
档案查回。登记只校验结构与范围，不拒绝日期重叠；重叠、空档和跨档都在验收选档时按方向报告。
"""
from .codec import digest, pack, unpack
from .errors import Problem
from .plan import MAX_LOSS
from .spans import find_span
from .trace import DIRECTIONS
from .values import day, fields, integer, key, rows, text

MAX_TIERS = 200


def _site_limits(raw, plan):
    wanted = {site['site_id'] for site in plan['sites']}
    limits = {}
    for raw_site in rows(raw, '档位点位限值', len(wanted), len(wanted)):
        site = fields(raw_site, 'site_id', 'limit_mdb')
        site_id = key(site['site_id'], '接续点编号')
        if site_id not in wanted:
            raise Problem(f'档位点位 {site_id} 不在光段计划中')
        if site_id in limits:
            raise Problem('档位内接续点编号必须唯一')
        limits[site_id] = integer(site['limit_mdb'], '档位点位限值', 0, MAX_LOSS)
    if set(limits) != wanted:
        raise Problem('档位点位限值必须覆盖光段的全部接续点')
    return [{'site_id': site['site_id'], 'limit_mdb': limits[site['site_id']]}
            for site in plan['sites']]


def tier_from(raw, plan):
    value = fields(raw, 'tier_id', 'label', 'start_on', 'end_on', 'site_limits',
                   'link_limit_mdb', 'residual_limit_mdb')
    start = day(value['start_on'], '档位起始日')
    end = day(value['end_on'], '档位截止日')
    if not start < end:
        raise Problem('档位截止日必须晚于起始日')
    return {
        'tier_id': key(value['tier_id'], '档位编号'),
        'label': text(value['label'], '档位名称'),
        'start_on': start,
        'end_on': end,
        'site_limits': _site_limits(value['site_limits'], plan),
        'link_limit_mdb': integer(value['link_limit_mdb'], '档位链路限值', 0, MAX_LOSS),
        'residual_limit_mdb': integer(value['residual_limit_mdb'], '档位闭合差限值', 0, MAX_LOSS),
    }


def registry_from(raw, plan):
    value = fields(raw, 'tiers')
    tiers = [tier_from(item, plan) for item in rows(value['tiers'], '限值档', 1, MAX_TIERS)]
    ids = set()
    for tier in tiers:
        if tier['tier_id'] in ids:
            raise Problem(f'档位编号重复：{tier["tier_id"]}')
        ids.add(tier['tier_id'])
    return {'tiers': sorted(tiers, key=lambda item: (item['start_on'], item['tier_id']))}


def versions(connection, span_id):
    find_span(connection, span_id)
    return [{'version': row['registry_version'], 'digest': row['digest'], 'registry': unpack(row['payload'])}
            for row in connection.execute(
                'SELECT registry_version, digest, payload FROM limit_tiers WHERE span_id = ? '
                'ORDER BY registry_version', (span_id,))]


def version_at(connection, span_id, version):
    row = connection.execute('SELECT digest, payload FROM limit_tiers WHERE span_id = ? AND registry_version = ?',
                             (span_id, version)).fetchone()
    if row is None:
        raise Problem('未找到该限值档登记版本', 404)
    return {'version': version, 'digest': row['digest'], 'registry': unpack(row['payload'])}


def archive(connection, span_id):
    row = connection.execute('SELECT version, stamp FROM span_registry WHERE span_id = ?', (span_id,)).fetchone()
    return {'registry_version': row['version'], 'stamp': row['stamp']} if row else {
        'registry_version': 0, 'stamp': 0}


def current(connection, span_id):
    value = archive(connection, span_id)
    if value['registry_version'] == 0:
        return {'version': 0, 'digest': None, 'tiers': []}
    entry = version_at(connection, span_id, value['registry_version'])
    return {'version': entry['version'], 'digest': entry['digest'], 'tiers': entry['registry']['tiers']}


def register(connection, span_id, raw):
    span = find_span(connection, span_id)
    registry = registry_from(raw, span['plan'])
    data = pack(registry)
    sha = digest(data)
    row = connection.execute('SELECT version FROM span_registry WHERE span_id = ?', (span_id,)).fetchone()
    if row is not None:
        latest = version_at(connection, span_id, row['version'])
        if latest['digest'] == sha:
            return {'version': latest['version'], 'digest': sha, 'registry': registry,
                    'archive': archive(connection, span_id), 'replayed': True}
    version = (row['version'] if row else 0) + 1
    if row is None:
        connection.execute('INSERT INTO span_registry(span_id, version, stamp) VALUES (?, ?, 1)', (span_id, version))
    else:
        connection.execute('UPDATE span_registry SET version = ?, stamp = stamp + 1 WHERE span_id = ?',
                           (version, span_id))
    connection.execute('INSERT INTO limit_tiers VALUES (?, ?, ?, ?)', (span_id, version, sha, data))
    return {'version': version, 'digest': sha, 'registry': registry,
            'archive': archive(connection, span_id), 'replayed': False}


def set_measured_on(connection, span_id, trace_id, raw):
    find_span(connection, span_id)
    value = day(fields(raw, 'measured_on')['measured_on'], '实测日期')
    if connection.execute('SELECT 1 FROM traces WHERE span_id = ? AND trace_id = ?',
                          (span_id, trace_id)).fetchone() is None:
        raise Problem('未找到该测量凭证', 404)
    old = connection.execute('SELECT measured_on FROM trace_dates WHERE span_id = ? AND trace_id = ?',
                             (span_id, trace_id)).fetchone()
    if old is not None and old['measured_on'] == value:
        return {'trace_id': trace_id, 'measured_on': value, 'archive': archive(connection, span_id),
                'revision': find_span(connection, span_id)['revision'], 'changed': False}
    connection.execute('INSERT INTO trace_dates(span_id, trace_id, measured_on) VALUES (?, ?, ?) '
                       'ON CONFLICT(span_id, trace_id) DO UPDATE SET measured_on = excluded.measured_on',
                       (span_id, trace_id, value))
    if archive(connection, span_id)['registry_version'] > 0:
        # 更订日期会让未签结论按当前登记重判；推高档案版本，使签发只能对应操作员看过的档案。
        connection.execute('UPDATE span_registry SET stamp = stamp + 1 WHERE span_id = ?', (span_id,))
    return {'trace_id': trace_id, 'measured_on': value, 'archive': archive(connection, span_id),
            'revision': find_span(connection, span_id)['revision'], 'changed': True}


def measured_dates(connection, span_id):
    return {row['trace_id']: row['measured_on'] for row in connection.execute(
        'SELECT trace_id, measured_on FROM trace_dates WHERE span_id = ?', (span_id,))}


def selected_dates(connection, span_id):
    from .selection import selected
    dates = measured_dates(connection, span_id)
    return {side: dates.get(item['trace']['trace_id'])
            for side, item in selected(connection, span_id).items() if item}


def inside(tier, measured_on):
    return tier['start_on'] <= measured_on < tier['end_on']


def tier_in_version(connection, span_id, version, tier_id):
    entry = version_at(connection, span_id, version)
    return next((tier for tier in entry['registry']['tiers'] if tier['tier_id'] == tier_id), None)


def resolve(registry, dates):
    """按两端实测日期选档。返回 (tier, problems)，problems 按方向列出。"""
    problems = []
    hits = {}
    labels = {'a': '甲端', 'b': '乙端'}
    for side in DIRECTIONS:
        measured_on = dates.get(side)
        if measured_on is None:
            problems.append({'direction': side, 'code': 'missing_date',
                             'message': f'{labels[side]}缺少实测日期'})
            continue
        matching = [tier for tier in registry['tiers'] if inside(tier, measured_on)]
        if not matching:
            problems.append({'direction': side, 'code': 'no_tier',
                             'message': f'{labels[side]}实测日期 {measured_on} 不落在任何限值档'})
        elif len(matching) > 1:
            names = '、'.join(tier['tier_id'] for tier in matching)
            problems.append({'direction': side, 'code': 'overlap',
                             'message': f'{labels[side]}实测日期 {measured_on} 同时命中档 {names}'})
        else:
            hits[side] = matching[0]
    tier = None
    if not problems and hits['a']['tier_id'] == hits['b']['tier_id']:
        tier = hits['a']
    elif not problems:
        problems.append({'direction': 'a', 'code': 'cross_tier',
                         'message': f'甲端命中档 {hits["a"]["tier_id"]}，乙端命中档 {hits["b"]["tier_id"]}'})
        problems.append({'direction': 'b', 'code': 'cross_tier',
                         'message': f'乙端命中档 {hits["b"]["tier_id"]}，甲端命中档 {hits["a"]["tier_id"]}'})
    return tier, problems


def describe(connection, span_id, dates=None, registry=None):
    info = archive(connection, span_id)
    if registry is None and info['registry_version'] > 0:
        registry = current(connection, span_id)
    dates = selected_dates(connection, span_id) if dates is None else dates
    if registry is None or registry['version'] == 0:
        return {'status': 'disabled', 'registry_version': 0, 'stamp': info['stamp'],
                'tier_id': None, 'tier': None, 'measured_on': dates, 'problems': []}
    tier, problems = resolve(registry, dates)
    return {'status': 'resolved' if tier else 'unresolved', 'registry_version': registry['version'],
            'stamp': info['stamp'], 'tier_id': tier['tier_id'] if tier else None, 'tier': tier,
            'measured_on': dates, 'problems': problems}
