from .budget import closure
from .matching import match
from .pairing import pair_sites

RULESET = 'splice-closure-v1'


def evaluate(span, active, traces):
    events, assigned = match(span['plan'], traces)
    sites = pair_sites(span['plan'], assigned)
    return {'ruleset': RULESET, 'revision': span['revision'], 'plan': span['plan'], 'active': active,
            'sites': sites, 'events': events, 'budget': closure(span['plan'], traces, sites, events)}
