"""整数毫分贝交割明细：在半格原读数上就近取整，满足每向点位合计守恒与全部限值。

半格网格上每个非整数读数恰为 x.5，floor 与 ceil 的绝对改动都是 0.5，因此所有满足
每向守恒的分配改动绝对值之和相同；并列时按计划里程、同点先甲后乙逐项比较，
在通过点位限值的候选中选择读数序列最小的一套。
"""
from .measure import as_fraction, canonical_number, half_away
from .trace import DIRECTIONS

# 同点候选按字典序：(甲上调, 乙上调)，越小越先取
_PAIR_ORDER = ((0, 0), (0, 1), (1, 0), (1, 1))


def _directional(traces, assigned, plan):
    """按计划里程整理每向完备点位的原读数、限值与来源事件。"""
    readings = {side: [] for side in DIRECTIONS}
    for index, site in enumerate(plan['sites']):
        for side in DIRECTIONS:
            event = assigned.get((side, site['site_id']))
            if event is None:
                return None
            readings[side].append({
                'order': index,
                'site_id': site['site_id'],
                'trace_id': event['trace_id'],
                'event_id': event['event_id'],
                'original': as_fraction(event['loss_mdb']),
                'limit': site['limit_mdb'],
            })
    totals = {}
    for side in DIRECTIONS:
        trace = next((item for item in traces if item['direction'] == side), None)
        if trace is None:
            return None
        totals[side] = as_fraction(trace['total_mdb'])
    return readings, totals


def _side_requirements(rows):
    """返回每点 floor、可上调标记，以及守恒要求的上调次数与目标合计。"""
    floors = []
    flexible = []
    raw_sum = as_fraction(0)
    for row in rows:
        original = row['original']
        raw_sum += original
        floor = original.numerator // original.denominator
        floors.append(floor)
        flexible.append(original != floor)
    target = half_away(raw_sum)
    raises = target - sum(floors)
    if raises < 0 or raises > sum(flexible):
        return None
    return floors, flexible, raises, target


def _lex_min_assignment(plan, requirements):
    """每向上调次数固定、点位双向合计不超限时，求字典序最小（里程，甲先乙后）分配。

    本质是两列 b-匹配：每个点位可在甲、乙各放至多一个上调，且同点上调总数不超过
    限值余量。逐点位按字典序尝试候选，并用后缀 Hall 条件（三个列子集）检验剩余
    需求是否仍可满足，第一个可行候选即字典序最优解，整体 O(n)。
    """
    floors = {side: requirements[side][0] for side in DIRECTIONS}
    flexible = {side: requirements[side][1] for side in DIRECTIONS}
    need = {side: requirements[side][2] for side in DIRECTIONS}
    count = len(plan['sites'])
    slack = []
    for index in range(count):
        room = 2 * plan['sites'][index]['limit_mdb'] - floors['a'][index] - floors['b'][index]
        if room < 0:
            return None
        slack.append(room)
    # 后缀资源：各向可用上调位、以及按点位限值折算的有效总容量（Hall 列子集条件）
    suffix_a = [0] * (count + 1)
    suffix_b = [0] * (count + 1)
    suffix_cap = [0] * (count + 1)
    for index in range(count - 1, -1, -1):
        suffix_a[index] = suffix_a[index + 1] + (1 if flexible['a'][index] and slack[index] >= 1 else 0)
        suffix_b[index] = suffix_b[index + 1] + (1 if flexible['b'][index] and slack[index] >= 1 else 0)
        eligible = (1 if flexible['a'][index] else 0) + (1 if flexible['b'][index] else 0)
        suffix_cap[index] = suffix_cap[index + 1] + min(slack[index], eligible)
    def feasible(index, remaining_a, remaining_b):
        return (remaining_a >= 0 and remaining_b >= 0
                and remaining_a <= suffix_a[index]
                and remaining_b <= suffix_b[index]
                and remaining_a + remaining_b <= suffix_cap[index])

    if not feasible(0, need['a'], need['b']):
        return None
    remaining = dict(need)
    pairs = []
    for index in range(count):
        chosen = None
        for up_a, up_b in _PAIR_ORDER:
            if up_a and not flexible['a'][index]:
                continue
            if up_b and not flexible['b'][index]:
                continue
            if up_a + up_b > slack[index]:
                continue
            next_a = remaining['a'] - up_a
            next_b = remaining['b'] - up_b
            if feasible(index + 1, next_a, next_b):
                chosen = (up_a, up_b)
                remaining['a'], remaining['b'] = next_a, next_b
                break
        if chosen is None:
            return None
        up_a, up_b = chosen
        pairs.append((floors['a'][index] + up_a, floors['b'][index] + up_b))
    if remaining['a'] != 0 or remaining['b'] != 0:
        return None
    return tuple(pairs)


def build_delivery(plan, traces, assigned, budget):
    blockers = list(budget.get('blockers', ()))
    source = _directional(traces, assigned, plan)
    if source is None:
        blockers.append('incomplete_sites')
        return {'status': 'held', 'blockers': sorted(set(blockers)), 'sites': [], 'totals_mdb': {}}
    readings, raw_totals = source
    requirements = {}
    totals = {}
    site_targets = {}
    for side in DIRECTIONS:
        requirements[side] = _side_requirements(readings[side])
        if requirements[side] is None:
            blockers.append('delivery_unallocable')
            return {'status': 'held', 'blockers': sorted(set(blockers)), 'sites': [], 'totals_mdb': {}}
        site_targets[side] = requirements[side][3]
        totals[side] = half_away(raw_totals[side])

    pairs = _lex_min_assignment(plan, requirements)
    if pairs is None:
        blockers.append('delivery_site_over_limit')
        return {'status': 'held', 'blockers': sorted(set(blockers)), 'sites': [], 'totals_mdb': totals}

    booked = {side: [pairs[index][offset] for index in range(len(pairs))]
              for offset, side in enumerate(DIRECTIONS)}

    fixed = 2 * plan['fixed_mdb']
    site_sum = sum(sum(booked[side]) for side in DIRECTIONS)
    estimate = fixed + site_sum
    measured = sum(totals.values())
    residual = measured - estimate
    if measured > 2 * plan['link_limit_mdb'] or estimate > 2 * plan['link_limit_mdb']:
        blockers.append('delivery_link_over_limit')
    if abs(residual) > 2 * plan['residual_limit_mdb']:
        blockers.append('delivery_closure_over_limit')
    if blockers:
        return {'status': 'held', 'blockers': sorted(set(blockers)), 'sites': [], 'totals_mdb': totals}

    sites = []
    for index, site in enumerate(plan['sites']):
        detail = {'site_id': site['site_id'], 'at_mm': site['at_mm'], 'limit_mdb': site['limit_mdb'],
                  'mean_x2_mdb': booked['a'][index] + booked['b'][index], 'observations': {}}
        for side in DIRECTIONS:
            row = readings[side][index]
            value = booked[side][index]
            detail['observations'][side] = {
                'trace_id': row['trace_id'], 'event_id': row['event_id'],
                'original_mdb': canonical_number(row['original']),
                'booked_mdb': value,
                'adjustment_mdb': canonical_number(value - row['original']),
            }
        sites.append(detail)
    return {'status': 'ready', 'blockers': [], 'sites': sites,
            'site_totals_mdb': site_targets,
            'totals_mdb': totals, 'estimate_x2_mdb': estimate,
            'measured_x2_mdb': measured, 'residual_x2_mdb': residual}
