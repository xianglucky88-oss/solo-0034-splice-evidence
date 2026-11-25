from .errors import Problem
from .receipts import get_trace
from .spans import find_span
from .trace import DIRECTIONS
from .values import fields, integer, key, rows
from .review import ROSTER_MAX, ROSTER_MIN
from .selection import require_revision, revision_from


def get_rosters(connection, span_id):
    """返回当前工作修订里两个方向的同向重测名单（无名单的方向为 None）。"""
    result = dict.fromkeys(DIRECTIONS)
    for direction in DIRECTIONS:
        entries = list(connection.execute(
            'SELECT trace_id, tolerance_mdb FROM review_rosters WHERE span_id = ? AND direction = ? '
            'ORDER BY position', (span_id, direction)))
        if entries:
            result[direction] = [dict(row) for row in entries]
    return result


def _load(connection, span_id, direction, trace_id):
    receipt = get_trace(connection, span_id, trace_id)
    if receipt['trace']['direction'] != direction:
        raise Problem('重测凭证方向与复核方向不一致')
    return receipt


def save_roster(connection, span_id, raw):
    fields(raw, 'revision', 'direction', 'tolerance_mdb', 'traces')
    direction = raw['direction']
    if direction not in DIRECTIONS:
        raise Problem('复核方向必须为 a 或 b')
    span = find_span(connection, span_id)
    require_revision(span, revision_from(raw['revision']))
    tolerance = integer(raw['tolerance_mdb'], '复核容差', 0, 2**31 - 1)
    raw_traces = rows(raw['traces'], '同向重测凭证', ROSTER_MIN, ROSTER_MAX)
    trace_ids = []
    for item in raw_traces:
        fields(item, 'trace_id')
        trace_ids.append(key(item['trace_id'], '凭证编号'))
    if len(set(trace_ids)) != len(trace_ids):
        raise Problem('复核名单中的凭证必须各不相同')

    receipts = [_load(connection, span_id, direction, trace_id) for trace_id in trace_ids]
    for other in DIRECTIONS:
        if other != direction and get_rosters(connection, span_id).get(other):
            raise Problem('另一端已建立同向重测名单，同一光段只能有一个方向采用多份重测')
    current = get_rosters(connection, span_id).get(direction) or []
    wanted = [{'trace_id': trace_id, 'tolerance_mdb': tolerance} for trace_id in trace_ids]
    if wanted == current:
        return {'revision': span['revision'], 'direction': direction, 'roster': wanted, 'changed': False}

    connection.execute('DELETE FROM review_rosters WHERE span_id = ? AND direction = ?', (span_id, direction))
    for position, trace_id in enumerate(trace_ids):
        connection.execute('INSERT INTO review_rosters VALUES (?, ?, ?, ?, ?)',
                           (span_id, direction, trace_id, position, tolerance))
    connection.execute('UPDATE spans SET revision = revision + 1 WHERE span_id = ?', (span_id,))
    return {'revision': span['revision'] + 1, 'direction': direction,
            'roster': wanted, 'digests': [item['digest'] for item in receipts], 'changed': True}


def clear_roster(connection, span_id, raw):
    fields(raw, 'revision', 'direction')
    direction = raw['direction']
    if direction not in DIRECTIONS:
        raise Problem('复核方向必须为 a 或 b')
    span = find_span(connection, span_id)
    require_revision(span, revision_from(raw['revision']))
    current = get_rosters(connection, span_id).get(direction)
    if not current:
        return {'revision': span['revision'], 'direction': direction, 'roster': [], 'changed': False}
    connection.execute('DELETE FROM review_rosters WHERE span_id = ? AND direction = ?', (span_id, direction))
    connection.execute('UPDATE spans SET revision = revision + 1 WHERE span_id = ?', (span_id,))
    return {'revision': span['revision'] + 1, 'direction': direction, 'roster': [], 'changed': True}
