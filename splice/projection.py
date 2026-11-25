from .budget import closure
from .matching import match
from .pairing import pair_sites, site_limits

RULESET = 'splice-closure-v1'


def summarize(span, active, traces, tier=None, tier_status=None, rated=True):
    events, assigned = match(span['plan'], traces)
    sites = pair_sites(span['plan'], assigned, site_limits(span['plan'], tier) if rated else None)
    if not rated:
        for site in sites:
            if site['status'] != 'incomplete':
                site['status'] = 'unrated'
    require_tier = tier_status is not None and tier_status['status'] == 'unresolved'
    return {'ruleset': RULESET, 'revision': span['revision'], 'plan': span['plan'], 'active': active,
            'sites': sites, 'events': events, 'rated': rated, 'tier': tier_status,
            'budget': closure(span['plan'], traces, sites, events, tier if rated else None, rated, require_tier)}


def evaluate(span, active, traces, tier_status):
    """disabled：按计划限值；resolved：按选中档；unresolved：留置但不判限值。"""
    status = tier_status['status']
    rated = status != 'unresolved'
    tier = tier_status['tier'] if status == 'resolved' else None
    return summarize(span, active, traces, tier, tier_status, rated)
