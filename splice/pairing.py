from .trace import DIRECTIONS


def pair_sites(plan, assigned):
    results = []
    for site in plan['sites']:
        observations = {side: assigned.get((side, site['site_id'])) for side in DIRECTIONS}
        if all(observations.values()):
            loss = sum(item['loss_mdb'] for item in observations.values())
            status = 'over' if loss > 2 * site['limit_mdb'] else 'pass'
        else:
            loss = None
            status = 'incomplete'
        results.append({**site, 'observations': observations, 'mean_x2_mdb': loss, 'status': status})
    return results
