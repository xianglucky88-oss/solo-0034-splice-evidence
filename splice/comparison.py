from .errors import Problem
from .releases import get_release


def compare(connection, span_id, left, right):
    before = get_release(connection, span_id, left)['snapshot']
    after = get_release(connection, span_id, right)['snapshot']
    if before['ruleset'] != after['ruleset'] or before['plan'] != after['plan']:
        raise Problem('两个签发版本的核算口径不同', 409)
    if after['mode'] == 'review':
        return _compare_review(left, right, before, after)

    changed = []
    prior_sites = {item['site_id']: item for item in before['sites']}
    for site in after['sites']:
        previous = prior_sites[site['site_id']]
        if previous != site:
            changed.append({'site_id': site['site_id'], 'before': previous, 'after': site,
                            'delta_x2_mdb': site['mean_x2_mdb'] - previous['mean_x2_mdb']})
    return {'from': left, 'to': right, 'sites': changed, 'before': before['budget'], 'after': after['budget'],
            'active_before': before['active'], 'active_after': after['active']}


def _compare_review(left, right, before, after):
    """同向复核版本按组内逐份闭合结果对齐比较。"""
    members_before = before['review']['members']
    members_after = after['review']['members']
    changed = []
    for trace_id in after['review']['group']:
        current = members_after.get(trace_id)
        previous = members_before.get(trace_id)
        if previous is None:
            changed.append({'trace_id': trace_id, 'kind': 'member_added', 'sites': current['sites']})
            continue
        site_changes = []
        prior_sites = {item['site_id']: item for item in previous['sites']}
        for site in current['sites']:
            old_site = prior_sites[site['site_id']]
            if old_site != site:
                site_changes.append({'site_id': site['site_id'], 'before': old_site, 'after': site,
                                     'delta_x2_mdb': (site['mean_x2_mdb'] - old_site['mean_x2_mdb'])
                                     if site['mean_x2_mdb'] is not None and old_site['mean_x2_mdb'] is not None
                                     else None})
        if site_changes or previous['residual_x2_mdb'] != current['residual_x2_mdb']:
            changed.append({'trace_id': trace_id, 'kind': 'member_changed', 'sites': site_changes,
                            'residual_before': previous['residual_x2_mdb'],
                            'residual_after': current['residual_x2_mdb']})
    return {'from': left, 'to': right, 'mode': 'review', 'members': changed,
            'review_before': before['review'], 'review_after': after['review'],
            'active_before': before['active'], 'active_after': after['active']}
