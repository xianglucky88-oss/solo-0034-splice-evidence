from .budget import closure
from .matching import match
from .pairing import pair_sites
from .review import review_plan

LEGACY_RULESET = 'splice-closure-v1'
REVIEW_RULESET = 'splice-review-v1'


def evaluate(span, active, traces):
    events, assigned = match(span['plan'], traces)
    sites = pair_sites(span['plan'], assigned)
    return {'ruleset': LEGACY_RULESET, 'mode': 'legacy', 'revision': span['revision'], 'plan': span['plan'],
            'active': active, 'sites': sites, 'events': events,
            'budget': closure(span['plan'], traces, sites, events)}


def evaluate_review(span, review_direction, entries, counter, counter_meta):
    """同向重测复核投影：entries 为名单凭证，counter 为另一端单份凭证。"""
    plan = span['plan']
    other_direction = next(side for side in ('a', 'b') if side != review_direction)
    result = review_plan(plan, review_direction, entries, counter)
    review = {key: value for key, value in result.items() if key != 'events'}
    active = {other_direction: counter_meta, review_direction: None}
    return {'ruleset': REVIEW_RULESET, 'mode': 'review', 'revision': span['revision'], 'plan': plan,
            'active': active, 'review': review, 'events': result['events'],
            'review_direction': review_direction,
            'budget': {'status': result['status'], 'blockers': result['blockers']}}
