from .trace import DIRECTIONS


def site_limits(plan, tier=None):
    """该档各点位限值；未启用限值档时退回计划限值。"""
    if tier is None:
        return {site['site_id']: site['limit_mdb'] for site in plan['sites']}
    return {item['site_id']: item['limit_mdb'] for item in tier['site_limits']}


def link_limits(plan, tier=None):
    if tier is None:
        return plan['link_limit_mdb'], plan['residual_limit_mdb']
    return tier['link_limit_mdb'], tier['residual_limit_mdb']


def closure(plan, traces, sites, events, tier=None, rated=True, require_tier=False):
    totals = {item['direction']: item['total_mdb'] for item in traces}
    blockers = []
    missing = [side for side in DIRECTIONS if side not in totals]
    if missing:
        blockers.append('missing_trace')
    if any(item['status'] != 'matched' for item in events):
        blockers.append('unassigned_events')
    complete = all(site['mean_x2_mdb'] is not None for site in sites)
    if not complete:
        blockers.append('incomplete_sites')
    if require_tier:
        blockers.append('tier_unresolved')
    if any(site['status'] == 'over' for site in sites):
        blockers.append('site_over_limit')
    estimated = 2 * plan['fixed_mdb'] + sum(site['mean_x2_mdb'] for site in sites) if complete else None
    measured = sum(totals.values()) if not missing else None
    residual = measured - estimated if measured is not None and estimated is not None else None
    link_limit, residual_limit = link_limits(plan, tier)
    if rated and any(value is not None and value > 2 * link_limit for value in (measured, estimated)):
        blockers.append('link_over_limit')
    if rated and residual is not None and abs(residual) > 2 * residual_limit:
        blockers.append('closure_over_limit')
    return {'status': 'held' if blockers else 'ready', 'blockers': blockers, 'totals_mdb': totals,
            'estimate_x2_mdb': estimated, 'measured_x2_mdb': measured, 'residual_x2_mdb': residual,
            'site_limits_mdb': site_limits(plan, tier) if rated else None,
            'link_limit_mdb': link_limit if rated else None,
            'residual_limit_mdb': residual_limit if rated else None}
