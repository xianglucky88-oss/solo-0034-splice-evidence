from .budget import closure
from .delivery import build_delivery
from .matching import match
from .pairing import pair_sites

RULESET = 'splice-closure-v2'


def evaluate(span, active, traces):
    events, assigned = match(span['plan'], traces)
    sites = pair_sites(span['plan'], assigned)
    budget = closure(span['plan'], traces, sites, events)
    delivery = build_delivery(span['plan'], traces, assigned, budget)
    return {'ruleset': RULESET, 'revision': span['revision'], 'plan': span['plan'], 'active': active,
            'sites': sites, 'events': events, 'budget': budget, 'delivery': delivery}
