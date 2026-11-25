from .errors import Problem
from .projection import evaluate, evaluate_review
from .rosters import get_rosters
from .selection import selected
from .spans import find_span


def workspace(connection, span_id):
    span = find_span(connection, span_id)
    rosters = get_rosters(connection, span_id)
    review_direction = next((side for side, roster in rosters.items() if roster), None)
    if review_direction is None:
        slots = selected(connection, span_id)
        traces = [item['trace'] for item in slots.values() if item]
        metadata = {side: {'trace_id': item['trace']['trace_id'], 'digest': item['digest']} if item else None
                    for side, item in slots.items()}
        return evaluate(span, metadata, traces)

    other_direction = next(side for side in rosters if side != review_direction)
    entries = []
    for row in rosters[review_direction]:
        receipt = _receipt(connection, span_id, row['trace_id'])
        entries.append({'trace_id': row['trace_id'], 'trace': receipt['trace'], 'digest': receipt['digest'],
                        'tolerance_mdb': row['tolerance_mdb']})
    slots = selected(connection, span_id)
    counter_slot = slots.get(other_direction)
    if counter_slot is None:
        raise Problem('一致性复核需要另一端先采用单份凭证', 409)
    counter_meta = {'trace_id': counter_slot['trace']['trace_id'], 'digest': counter_slot['digest']}
    return evaluate_review(span, review_direction, entries, counter_slot['trace'], counter_meta)


def _receipt(connection, span_id, trace_id):
    from .receipts import get_trace
    return get_trace(connection, span_id, trace_id)


def event_evidence(result, trace_id, event_id):
    for item in result['events']:
        if item['trace_id'] == trace_id and item['event_id'] == event_id:
            return {'revision': result['revision'], 'event': item,
                    'sites': [site for site in result['plan']['sites'] if site['site_id'] in item['candidates']]}
    raise Problem('所选修订中没有这条仪表事件', 404)
