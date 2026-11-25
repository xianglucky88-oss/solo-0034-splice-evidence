from .errors import Problem
from .projection import evaluate
from .registration import CALIBRATION_STATUS, HELD_REASON, ROLE_LABEL
from .selection import selected
from .spans import find_span


def workspace(connection, span_id):
    span = find_span(connection, span_id)
    slots = selected(connection, span_id)
    traces = [item['trace'] for item in slots.values() if item]
    metadata = {side: {'trace_id': item['trace']['trace_id'], 'digest': item['digest']} if item else None
                for side, item in slots.items()}
    return evaluate(span, metadata, traces)


def event_evidence(result, trace_id, event_id):
    for item in result['events']:
        if item['trace_id'] == trace_id and item['event_id'] == event_id:
            calibration = next((entry for entry in result.get('calibrations', ())
                                if entry['trace_id'] == trace_id), None)
            return {'revision': result['revision'], 'event': item,
                    'sites': [site for site in result['sites'] if site['site_id'] in item['candidates']],
                    'calibration': calibration,
                    'mark_labels': ROLE_LABEL,
                    'calibration_status': CALIBRATION_STATUS,
                    'held_reason': HELD_REASON}
    raise Problem('所选修订中没有这条仪表事件', 404)
