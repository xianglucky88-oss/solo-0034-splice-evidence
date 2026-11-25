from .errors import Problem
from .limits import describe
from .projection import evaluate
from .selection import selected
from .spans import find_span


def workspace(connection, span_id):
    span = find_span(connection, span_id)
    slots = selected(connection, span_id)
    traces = [item['trace'] for item in slots.values() if item]
    metadata = {side: {'trace_id': item['trace']['trace_id'], 'digest': item['digest']} if item else None
                for side, item in slots.items()}
    return evaluate(span, metadata, traces, describe(connection, span_id))


def event_evidence(result, trace_id, event_id):
    for item in result['events']:
        if item['trace_id'] == trace_id and item['event_id'] == event_id:
            return {'revision': result['revision'], 'event': item,
                    'sites': [site for site in result['sites'] if site['site_id'] in item['candidates']]}
    raise Problem('所选修订中没有这条仪表事件', 404)
