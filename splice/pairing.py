from .trace import DIRECTIONS


def site_limits(plan, tier=None):
    """该档各点位限值；未启用限值档时退回计划限值。"""
    if tier is None:
        return {site['site_id']: site['limit_mdb'] for site in plan['sites']}
    return {item['site_id']: item['limit_mdb'] for item in tier['site_limits']}


def pair_sites(plan, assigned, limits):
    """limits 为 None 时沿用计划限值；否则使用选定档位的点位限值。"""
    results = []
    for site in plan['sites']:
        observations = {side: assigned.get((side, site['site_id'])) for side in DIRECTIONS}
        complete = all(observations.values())
        loss = sum(item['loss_mdb'] for item in observations.values()) if complete else None
        cap = site['limit_mdb'] if limits is None else limits[site['site_id']]
        if not complete:
            status = 'incomplete'
        else:
            status = 'over' if loss > 2 * cap else 'pass'
        results.append({**site, 'observations': observations, 'mean_x2_mdb': loss, 'limit_mdb': cap,
                        'plan_limit_mdb': site['limit_mdb'], 'status': status})
    return results
