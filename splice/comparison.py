from .errors import Problem
from .releases import get_release


def compare(connection, span_id, left, right):
    before = get_release(connection, span_id, left)['snapshot']
    after = get_release(connection, span_id, right)['snapshot']
    if before['ruleset'] != after['ruleset'] or before['plan'] != after['plan']:
        raise Problem('两个签发版本的核算口径不同', 409)
    changed = []
    prior_sites = {item['site_id']: item for item in before['sites']}
    for site in after['sites']:
        previous = prior_sites[site['site_id']]
        if previous != site:
            changed.append({'site_id': site['site_id'], 'before': previous, 'after': site,
                            'delta_x2_mdb': site['mean_x2_mdb'] - previous['mean_x2_mdb']})
    delivery_changed = before['delivery'] != after['delivery']
    return {'from': left, 'to': right, 'sites': changed, 'before': before['budget'], 'after': after['budget'],
            'active_before': before['active'], 'active_after': after['active'],
            'delivery_before': before['delivery'], 'delivery_after': after['delivery'],
            'delivery_changed': delivery_changed}
