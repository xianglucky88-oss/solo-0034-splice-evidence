from .measure import as_fraction, canonical_number
from .trace import DIRECTIONS


def closure(plan, traces, sites, events):
    totals = {item['direction']: as_fraction(item['total_mdb']) for item in traces}
    blockers = []
    missing = [side for side in DIRECTIONS if side not in totals]
    if missing:
        blockers.append('missing_trace')
    if any(item['status'] != 'matched' for item in events):
        blockers.append('unassigned_events')
    complete = all(site['mean_x2_mdb'] is not None for site in sites)
    if not complete:
        blockers.append('incomplete_sites')
    if any(site['status'] == 'over' for site in sites):
        blockers.append('site_over_limit')
    if complete:
        estimate = 2 * plan['fixed_mdb'] + sum(
            (as_fraction(site['mean_x2_mdb']) for site in sites), start=as_fraction(0))
    else:
        estimate = None
    measured = sum(totals.values(), start=as_fraction(0)) if not missing else None
    residual = measured - estimate if measured is not None and estimate is not None else None
    limit = 2 * plan['link_limit_mdb']
    if any(value is not None and value > limit for value in (measured, estimate)):
        blockers.append('link_over_limit')
    if residual is not None and abs(residual) > 2 * plan['residual_limit_mdb']:
        blockers.append('closure_over_limit')
    return {
        'status': 'held' if blockers else 'ready',
        'blockers': blockers,
        'totals_mdb': {side: canonical_number(value) for side, value in totals.items()},
        'estimate_x2_mdb': None if estimate is None else canonical_number(estimate),
        'measured_x2_mdb': None if measured is None else canonical_number(measured),
        'residual_x2_mdb': None if residual is None else canonical_number(residual),
    }
