"""同向重测一致性复核。

一端反复扫测形成多份同向凭证时，本模块独立按原计划归点，先判断每份凭证能否
入组（每个点位恰有一条唯一归点事件且没有待处置事件），再按容差比较任两份
凭证的逐点单端损耗差与整段实测差，选出唯一且过半的最大相容组，最后让组内
每份凭证与另一端单份凭证逐份核算点位、整段和闭合限值。
"""
from collections import defaultdict

from .registration import coordinate, encoded
from .trace import DIRECTIONS
from .windows import index_windows, candidates

ROSTER_MIN = 3
ROSTER_MAX = 9

# 待处置事件状态 → 未入组原因码
PENDING_REASON = {
    'outside': 'event_outside',
    'unmapped': 'event_unmapped',
    'ambiguous': 'event_ambiguous',
    'collision': 'event_collision',
}


def trace_outcomes(plan, trace):
    """对单份凭证独立按原计划归点，返回事件行与点位命中表。"""
    windows = index_windows(plan['sites'])
    events = []
    singles = defaultdict(list)
    for line, event in enumerate(trace['events'], 1):
        position = coordinate(trace, event['at_mm'], plan['length_mm'])
        eligible = [] if position is None else candidates(windows, position)
        item = {**event, 'line': line, 'trace_id': trace['trace_id'], 'direction': trace['direction'],
                'along_mm': encoded(position), 'candidates': eligible}
        if position is None:
            item['status'] = 'outside'
        elif not eligible:
            item['status'] = 'unmapped'
        elif len(eligible) > 1:
            item['status'] = 'ambiguous'
        else:
            item['status'] = 'matched'
            singles[eligible[0]].append(item)
        events.append(item)
    assigned = {}
    for site_id, items in singles.items():
        if len(items) == 1:
            assigned[site_id] = items[0]
        else:
            for item in items:
                item['status'] = 'collision'
    return events, assigned


def eligibility(plan, trace):
    """返回 (是否可入组, 未入组原因)。"""
    events, assigned = trace_outcomes(plan, trace)
    pending = [{'event_id': item['event_id'], 'reason': PENDING_REASON[item['status']]}
               for item in events if item['status'] != 'matched']
    missing = [site['site_id'] for site in plan['sites'] if site['site_id'] not in assigned]
    if pending or missing:
        detail = {}
        if pending:
            detail['events'] = pending
        if missing:
            detail['missing_sites'] = missing
        return False, {'code': 'pending_events', 'detail': detail}, events, assigned
    return True, None, events, assigned


def compatible(first, second, tolerance_mdb):
    """两份可入组凭证逐点单端损耗差与整段实测差均不超容差才相容。"""
    failures = []
    for site_id, first_event in first['assigned'].items():
        delta = abs(first_event['loss_mdb'] - second['assigned'][site_id]['loss_mdb'])
        if delta > tolerance_mdb:
            failures.append({'kind': 'site', 'site_id': site_id, 'delta_mdb': delta})
    total_delta = abs(first['trace']['total_mdb'] - second['trace']['total_mdb'])
    if total_delta > tolerance_mdb:
        failures.append({'kind': 'total', 'delta_mdb': total_delta})
    return not failures, failures


def maximum_cliques(nodes, edges):
    """Bron–Kerbosch（带支点）枚举全部极大团，再取最大团。"""
    neighbors = {node: set() for node in nodes}
    for left, right in edges:
        neighbors[left].add(right)
        neighbors[right].add(left)
    found = []

    def search(required, candidates_, excluded):
        if not candidates_ and not excluded:
            found.append(frozenset(required))
            return
        pivot = max(candidates_ | excluded, key=lambda node: len(neighbors[node] & candidates_))
        for node in sorted(candidates_ - neighbors[pivot]):
            search(required | {node}, candidates_ & neighbors[node], excluded & neighbors[node])
            candidates_ = candidates_ - {node}
            excluded = excluded | {node}

    search(set(), set(nodes), set())
    if not found:
        return []
    largest = max(len(clique) for clique in found)
    return [sorted(clique) for clique in found if len(clique) == largest]


def member_budget(plan, trace, assigned, counter, counter_assigned, counter_ok):
    """组内一份凭证与另一端单份凭证逐份核算闭合结果。"""
    sites = []
    site_blocked = False
    for site in plan['sites']:
        own = assigned.get(site['site_id'])
        other = counter_assigned.get(site['site_id'])
        if own is not None and other is not None and counter_ok:
            loss_x2 = own['loss_mdb'] + other['loss_mdb']
            status = 'over' if loss_x2 > 2 * site['limit_mdb'] else 'pass'
            site_blocked = site_blocked or status == 'over'
        else:
            loss_x2 = None
            status = 'incomplete'
        sites.append({'site_id': site['site_id'], 'at_mm': site['at_mm'], 'limit_mdb': site['limit_mdb'],
                      'own_event_id': own['event_id'] if own else None,
                      'counter_event_id': other['event_id'] if other else None,
                      'mean_x2_mdb': loss_x2, 'status': status})
    blockers = []
    if not counter_ok or any(item['status'] != 'pass' for item in sites):
        if site_blocked:
            blockers.append('review_site_over_limit')
        if not counter_ok:
            blockers.append('review_counter_pending')
    complete = all(item['mean_x2_mdb'] is not None for item in sites)
    estimate = 2 * plan['fixed_mdb'] + sum(item['mean_x2_mdb'] for item in sites) if complete else None
    measured = trace['total_mdb'] + counter['total_mdb'] if counter_ok else None
    residual = measured - estimate if measured is not None and estimate is not None else None
    link_limit = 2 * plan['link_limit_mdb']
    if any(value is not None and value > link_limit for value in (measured, estimate)):
        blockers.append('review_link_over_limit')
    if residual is not None and abs(residual) > 2 * plan['residual_limit_mdb']:
        blockers.append('review_closure_over_limit')
    return {'trace_id': trace['trace_id'], 'sites': sites, 'blockers': blockers,
            'estimate_x2_mdb': estimate, 'measured_x2_mdb': measured, 'residual_x2_mdb': residual,
            'status': 'held' if blockers else 'ready'}


def review_plan(plan, review_direction, entries, counter):
    """执行一次完整的同向重测一致性复核。

    entries 为按名单顺序排列的 [{trace_id, trace, digest, tolerance_mdb}]，
    counter 为另一端单份凭证。
    """
    other_direction = next(side for side in DIRECTIONS if side != review_direction)
    roster_ids = [entry['trace_id'] for entry in entries]
    tolerance = entries[0]['tolerance_mdb']
    prepared = []
    all_events = []
    for entry in entries:
        ok, reason, events, assigned = eligibility(plan, entry['trace'])
        all_events.extend(events)
        prepared.append({**entry, 'eligible': ok, 'exclusion': reason, 'events': events, 'assigned': assigned})

    eligible = [item for item in prepared if item['eligible']]
    edges = []
    pair_failures = defaultdict(list)
    for index, first in enumerate(eligible):
        for second in eligible[index + 1:]:
            ok, failures = compatible(first, second, tolerance)
            if ok:
                edges.append((first['trace_id'], second['trace_id']))
            else:
                pair_failures[first['trace_id']].append({'trace_id': second['trace_id'], 'failures': failures})
                pair_failures[second['trace_id']].append({'trace_id': first['trace_id'], 'failures': failures})

    largest = maximum_cliques([item['trace_id'] for item in eligible], edges)
    group = largest[0] if len(largest) == 1 and len(largest[0]) * 2 > len(entries) else None

    counter_ok, _, counter_events, counter_assigned = eligibility(plan, counter)
    all_events.extend(counter_events)

    members = {}
    blockers = []
    if group is None:
        blockers.append('review_no_majority')
    else:
        grouped = set(group)
        for item in prepared:
            if item['trace_id'] in grouped:
                result = member_budget(plan, item['trace'], item['assigned'],
                                       counter, counter_assigned, counter_ok)
                members[item['trace_id']] = result
                blockers.extend(code for code in result['blockers'] if code not in blockers)

    roster = []
    for item in prepared:
        exclusion = None
        if not item['eligible']:
            exclusion = item['exclusion']
        elif group is None or item['trace_id'] not in group:
            if group is None:
                exclusion = {'code': 'no_unique_majority_group',
                             'detail': {'conflicts': pair_failures.get(item['trace_id'], [])}}
            else:
                exclusion = {'code': 'outside_largest_group',
                             'detail': {'conflicts': pair_failures.get(item['trace_id'], [])}}
        roster.append({'trace_id': item['trace_id'], 'digest': item['digest'],
                       'tolerance_mdb': item['tolerance_mdb'], 'eligible': item['eligible'],
                       'exclusion': exclusion})

    return {
        'direction': review_direction,
        'counter_direction': other_direction,
        'tolerance_mdb': tolerance,
        'roster': roster,
        'roster_ids': roster_ids,
        'group': group or [],
        'blockers': blockers,
        'members': members,
        'events': all_events,
        'status': 'held' if blockers else 'ready',
    }
