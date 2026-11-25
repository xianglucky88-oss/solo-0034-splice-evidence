from .errors import Problem
from .releases import get_release


def compare(connection, span_id, left, right):
    before = get_release(connection, span_id, left)
    after = get_release(connection, span_id, right)
    first, second = before['snapshot'], after['snapshot']
    if first['ruleset'] != second['ruleset'] or first['plan'] != second['plan']:
        raise Problem('两个签发版本的核算口径不同', 409)
    prior_sites = {item['site_id']: item for item in first['sites']}
    changed = []
    for site in second['sites']:
        previous = prior_sites[site['site_id']]
        if previous != site:
            changed.append({'site_id': site['site_id'], 'before': previous, 'after': site,
                            'delta_x2_mdb': site['mean_x2_mdb'] - previous['mean_x2_mdb']})
    return {'from': left, 'to': right, 'sites': changed, 'before': first['budget'], 'after': second['budget'],
            'active_before': first['active'], 'active_after': second['active'],
            'handoff_before': before['handoff'], 'handoff_after': after['handoff'],
            'digest_before': before['digest'], 'digest_after': after['digest']}
