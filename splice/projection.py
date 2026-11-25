from .budget import closure
from .matching import match
from .pairing import pair_sites

RULESET = 'splice-closure-v1'


def evaluate(span, active, traces, handoff=None, sources=None):
    events, assigned = match(span['plan'], traces)
    sites = pair_sites(span['plan'], assigned)
    budget = closure(span['plan'], traces, sites, events)
    handoff = handoff or {'status': 'clear', 'adopted': [], 'affected': []}
    if handoff['status'] != 'clear':
        budget = {**budget, 'status': 'held', 'blockers': [*budget['blockers'], 'revoked_calibration']}
    sources = sources or {}
    for item in events:
        source = sources.get(item['trace_id'])
        if source:
            item['credential'] = source['credential']
            item['notice'] = source['notice']
    return {'ruleset': RULESET, 'revision': span['revision'], 'plan': span['plan'], 'active': active,
            'sites': sites, 'events': events, 'budget': budget, 'handoff': handoff}
