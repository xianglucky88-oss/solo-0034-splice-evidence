from .errors import Problem
from .values import fields, key, rows

RELATIONS = ('split', 'merge', 'continue', 'added', 'retired')
# 关系两侧对点位的基数与出现侧要求：from 侧（旧版）、to 侧（新版）
SHAPE = {
    'split': {'from': 1, 'to': (2, None)},
    'merge': {'from': (2, None), 'to': 1},
    'continue': {'from': 1, 'to': 1},
    'added': {'from': 0, 'to': 1},
    'retired': {'from': 1, 'to': 0},
}


def _bound(value, shape):
    low, high = shape if isinstance(shape, tuple) else (shape, shape)
    if value < low or (high is not None and value > high):
        raise Problem('拆并换版关系的点位数量不符合工程语义')


def _site_ref(value, field, known):
    site_id = key(value, field)
    if site_id not in known:
        raise Problem(f'{field} 引用的点位不在对应版本计划中：{site_id}')
    return site_id


def relations_from(raw, parent_plan, new_plan):
    value = fields(raw, 'basis', 'relations')
    basis = value['basis']
    if not isinstance(basis, str) or not 1 <= len(basis.strip()) <= 200:
        raise Problem('计划依据必须为 1 至 200 个字符')
    parent_sites = {site['site_id'] for site in parent_plan['sites']}
    new_sites = {site['site_id'] for site in new_plan['sites']}
    parent_limits = {site['site_id']: site['limit_mdb'] for site in parent_plan['sites']}
    new_limits = {site['site_id']: site['limit_mdb'] for site in new_plan['sites']}
    seen_from, seen_to = [], []
    normalized = []
    for item in rows(value['relations'], '工程关系', 1, 1000):
        relation = fields(item, 'relation', 'from_sites', 'to_sites')['relation']
        if relation not in RELATIONS:
            raise Problem('工程关系必须为 split、merge、continue、added 或 retired')
        from_sites = [_site_ref(v, '旧版点位', parent_sites)
                      for v in rows(item['from_sites'], '旧版点位', 0, 500)]
        to_sites = [_site_ref(v, '新版点位', new_sites)
                    for v in rows(item['to_sites'], '新版点位', 0, 500)]
        if len(from_sites) != len(set(from_sites)) or len(to_sites) != len(set(to_sites)):
            raise Problem('同一关系内点位不得重复')
        _bound(len(from_sites), SHAPE[relation]['from'])
        _bound(len(to_sites), SHAPE[relation]['to'])
        if relation == 'continue':
            old_id, new_id = from_sites[0], to_sites[0]
            if parent_limits[old_id] != new_limits[new_id]:
                raise Problem('沿用关系必须沿用原判限')
        seen_from.extend(from_sites)
        seen_to.extend(to_sites)
        normalized.append({'relation': relation, 'from_sites': from_sites, 'to_sites': to_sites})
    # 两版每点恰归一项：旧版点与新版点各自完整划分，不重不漏
    if sorted(seen_from) != sorted(parent_sites) or sorted(seen_to) != sorted(new_sites):
        raise Problem('两版每个点位必须恰好归入一项拆并换版关系')
    return basis.strip(), normalized
