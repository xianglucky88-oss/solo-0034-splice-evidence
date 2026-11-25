from .errors import Problem
from .limits import tier_in_version
from .releases import get_release
from .spans import find_span


def _limits(snapshot):
    budget = snapshot['budget']
    if budget.get('link_limit_mdb') is not None:
        return {'sites': budget.get('site_limits_mdb') or
                {site['site_id']: site['limit_mdb'] for site in snapshot['sites']},
                'link': budget['link_limit_mdb'], 'residual': budget['residual_limit_mdb']}
    plan = snapshot['plan']
    return {'sites': {site['site_id']: site['limit_mdb'] for site in snapshot['sites']},
            'link': plan['link_limit_mdb'], 'residual': plan['residual_limit_mdb']}


def _tier_of(snapshot):
    tier = snapshot.get('tier') or {}
    if tier.get('tier_id'):
        return {'registry_version': tier.get('registry_version'), 'tier_id': tier['tier_id'],
                'label': (tier.get('tier') or {}).get('label')}
    return None


def _judge(snapshot, tier):
    """用给定档位重判一份签件；不改变原始结论。"""
    plan = snapshot['plan']
    limits = {item['site_id']: item['limit_mdb'] for item in tier['site_limits']}
    sites = []
    for site in snapshot['sites']:
        mean = site['mean_x2_mdb']
        cap = limits[site['site_id']]
        status = 'incomplete' if mean is None else ('over' if mean > 2 * cap else 'pass')
        sites.append({'site_id': site['site_id'], 'mean_x2_mdb': mean, 'limit_mdb': cap, 'status': status})
    complete = all(site['mean_x2_mdb'] is not None for site in sites)
    estimated = 2 * plan['fixed_mdb'] + sum(site['mean_x2_mdb'] for site in sites) if complete else None
    totals = snapshot['budget']['totals_mdb']
    measured = sum(totals.values()) if totals else None
    residual = measured - estimated if measured is not None and estimated is not None else None
    blockers = []
    if any(site['status'] == 'incomplete' for site in sites):
        blockers.append('incomplete_sites')
    if any(site['status'] == 'over' for site in sites):
        blockers.append('site_over_limit')
    if any(value is not None and value > 2 * tier['link_limit_mdb'] for value in (measured, estimated)):
        blockers.append('link_over_limit')
    if residual is not None and abs(residual) > 2 * tier['residual_limit_mdb']:
        blockers.append('closure_over_limit')
    return {'tier_id': tier['tier_id'], 'label': tier['label'], 'status': 'held' if blockers else 'ready',
            'blockers': blockers, 'sites': sites, 'estimate_x2_mdb': estimated, 'measured_x2_mdb': measured,
            'residual_x2_mdb': residual, 'link_limit_mdb': tier['link_limit_mdb'],
            'residual_limit_mdb': tier['residual_limit_mdb']}


def _option(connection, span_id, snapshot):
    tier = _tier_of(snapshot)
    if tier is None:
        return None
    found = tier_in_version(connection, span_id, tier['registry_version'], tier['tier_id'])
    if found is None:
        return None
    return {'registry_version': tier['registry_version'], 'tier_id': tier['tier_id'], 'tier': found}


def _rejudge_options(connection, span_id, before, after):
    options = []
    seen = set()
    for snapshot in (before, after):
        option = _option(connection, span_id, snapshot)
        if option and (option['registry_version'], option['tier_id']) not in seen:
            seen.add((option['registry_version'], option['tier_id']))
            options.append(option)
    return options


def compare(connection, span_id, left, right, version=None, tier_id=None):
    find_span(connection, span_id)
    before = get_release(connection, span_id, left)
    after = get_release(connection, span_id, right)
    before_snapshot, after_snapshot = before['snapshot'], after['snapshot']
    if before_snapshot['plan'] != after_snapshot['plan']:
        raise Problem('两个签发版本的计划口径不同', 409)
    changed = []
    prior = {item['site_id']: item for item in before_snapshot['sites']}
    for site in after_snapshot['sites']:
        previous = prior[site['site_id']]
        if previous != site:
            changed.append({'site_id': site['site_id'], 'before': previous, 'after': site,
                            'delta_x2_mdb': site['mean_x2_mdb'] - previous['mean_x2_mdb']})
    measurement = {
        'sites': [{'site_id': site['site_id'], 'before_x2_mdb': prior[site['site_id']]['mean_x2_mdb'],
                   'after_x2_mdb': site['mean_x2_mdb'],
                   'delta_x2_mdb': site['mean_x2_mdb'] - prior[site['site_id']]['mean_x2_mdb']}
                  for site in after_snapshot['sites']],
        'measured_before_mdb': before_snapshot['budget']['measured_x2_mdb'],
        'measured_after_mdb': after_snapshot['budget']['measured_x2_mdb'],
    }
    measurement['measured_delta_mdb'] = (
        None if measurement['measured_before_mdb'] is None or measurement['measured_after_mdb'] is None
        else measurement['measured_after_mdb'] - measurement['measured_before_mdb'])
    accounting = {
        'estimate_before_mdb': before_snapshot['budget']['estimate_x2_mdb'],
        'estimate_after_mdb': after_snapshot['budget']['estimate_x2_mdb'],
        'residual_before_mdb': before_snapshot['budget']['residual_x2_mdb'],
        'residual_after_mdb': after_snapshot['budget']['residual_x2_mdb'],
    }
    prior_limits, after_limits = _limits(before_snapshot), _limits(after_snapshot)
    limits = {
        'sites': [{'site_id': site['site_id'], 'before_mdb': prior_limits['sites'].get(site['site_id']),
                   'after_mdb': after_limits['sites'].get(site['site_id'])}
                  for site in after_snapshot['sites']],
        'link': {'before_mdb': prior_limits['link'], 'after_mdb': after_limits['link']},
        'residual': {'before_mdb': prior_limits['residual'], 'after_mdb': after_limits['residual']},
    }
    result = {'from': left, 'to': right, 'sites': changed,
              'before': before_snapshot['budget'], 'after': after_snapshot['budget'],
              'active_before': before_snapshot['active'], 'active_after': after_snapshot['active'],
              'tier_before': _tier_of(before_snapshot), 'tier_after': _tier_of(after_snapshot),
              'measurement': measurement, 'accounting': accounting, 'limits': limits,
              'rejudge_options': [{'registry_version': item['registry_version'], 'tier_id': item['tier_id'],
                                   'label': item['tier']['label']}
                                  for item in _rejudge_options(connection, span_id, before_snapshot, after_snapshot)]}
    if version is not None:
        result['rejudge'] = _rejudge(connection, span_id, before_snapshot, after_snapshot, version, tier_id,
                                     before['digest'], after['digest'])
    return result


def _rejudge(connection, span_id, before_snapshot, after_snapshot, version, tier_id, before_digest,
             after_digest):
    options = {(item['registry_version'], item['tier_id']): item
               for item in _rejudge_options(connection, span_id, before_snapshot, after_snapshot)}
    chosen = options.get((version, tier_id))
    if chosen is None:
        raise Problem('所选限值档不是任一原件实际采用的同范围档位', 422)
    tier = chosen['tier']
    return {'registry_version': version, 'tier_id': tier_id, 'label': tier['label'],
            'before': {'digest': before_digest, 'original': before_snapshot['budget'],
                       'tier': _tier_of(before_snapshot), 'judgment': _judge(before_snapshot, tier)},
            'after': {'digest': after_digest, 'original': after_snapshot['budget'],
                      'tier': _tier_of(after_snapshot), 'judgment': _judge(after_snapshot, tier)}}
