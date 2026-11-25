from .trace import DIRECTIONS


def closure(plan, traces, sites, events, calibrations=()):
    totals = {item['direction']: item['total_mdb'] for item in traces}
    blockers = []
    missing = [side for side in DIRECTIONS if side not in totals]
    if missing:
        blockers.append('missing_trace')
    if any(item['status'] == 'held' for item in calibrations):
        blockers.append('calibration_held')
    if any(item['status'] not in ('matched', 'held') for item in events):
        blockers.append('unassigned_events')
    complete = all(site['mean_x2_mdb'] is not None for site in sites)
    if not complete:
        blockers.append('incomplete_sites')
    if any(site['status'] == 'over' for site in sites):
        blockers.append('site_over_limit')
    estimated = 2 * plan['fixed_mdb'] + sum(site['mean_x2_mdb'] for site in sites) if complete else None
    measured = sum(totals.values()) if not missing else None
    residual = measured - estimated if measured is not None and estimated is not None else None
    limit = 2 * plan['link_limit_mdb']
    if any(value is not None and value > limit for value in (measured, estimated)):
        blockers.append('link_over_limit')
    if residual is not None and abs(residual) > 2 * plan['residual_limit_mdb']:
        blockers.append('closure_over_limit')
    return {'status': 'held' if blockers else 'ready', 'blockers': blockers, 'totals_mdb': totals,
            'estimate_x2_mdb': estimated, 'measured_x2_mdb': measured, 'residual_x2_mdb': residual}
