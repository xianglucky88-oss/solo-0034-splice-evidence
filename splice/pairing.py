from .measure import as_fraction, canonical_number
from .trace import DIRECTIONS


def pair_sites(plan, assigned):
    results = []
    for site in plan['sites']:
        observations = {side: assigned.get((side, site['site_id'])) for side in DIRECTIONS}
        if all(observations.values()):
            loss = sum((as_fraction(item['loss_mdb']) for item in observations.values()),
                       start=as_fraction(0))
            status = 'over' if loss > 2 * site['limit_mdb'] else 'pass'
            loss_value = canonical_number(loss)
        else:
            loss_value = None
            status = 'incomplete'
        results.append({**site, 'observations': observations, 'mean_x2_mdb': loss_value, 'status': status})
    return results
