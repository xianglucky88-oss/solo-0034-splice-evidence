from .errors import Problem
from .projection import evaluate
from .revocations import assess_release, notice_pairs, trace_identity
from .selection import selected
from .spans import find_span


def workspace(connection, span_id):
    span = find_span(connection, span_id)
    slots = selected(connection, span_id)
    traces = [item['trace'] for item in slots.values() if item]
    pairs = notice_pairs(connection)
    metadata = {}
    sources = {}
    for side, item in slots.items():
        if item:
            source = trace_identity(item['trace'])
            notice = pairs.get((source['instrument_id'], source['calibration_batch'])) if source['source'] == 'stated' else None
            metadata[side] = {'trace_id': item['trace']['trace_id'], 'digest': item['digest'], **source}
            sources[item['trace']['trace_id']] = {'credential': source, 'notice': notice}
        else:
            metadata[side] = None
    handoff = assess_release(connection, span_id, {'active': metadata}, pairs)
    return evaluate(span, metadata, traces, handoff, sources)


def event_evidence(result, trace_id, event_id):
    for item in result['events']:
        if item['trace_id'] == trace_id and item['event_id'] == event_id:
            meta = (result.get('active') or {}).get(item['direction'])
            notices = {entry.get('trace_id'): entry.get('notice') for entry in (result.get('handoff') or {}).get('adopted', [])}
            return {'revision': result['revision'], 'event': item,
                    'sites': [site for site in result['sites'] if site['site_id'] in item['candidates']],
                    'credential': item.get('credential') or (trace_identity(meta) if meta else None),
                    'notice': item.get('notice') or notices.get(trace_id)}
    raise Problem('所选修订中没有这条仪表事件', 404)
