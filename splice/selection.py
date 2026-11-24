from .errors import Problem
from .receipts import get_trace
from .spans import find_span
from .trace import DIRECTIONS
from .values import fields, integer, key


def selected(connection, span_id):
    slots = dict.fromkeys(DIRECTIONS)
    for row in connection.execute('SELECT direction, trace_id FROM active_traces WHERE span_id = ?', (span_id,)):
        receipt = get_trace(connection, span_id, row['trace_id'])
        slots[row['direction']] = receipt
    return slots


def revision_from(value):
    return integer(value, '工作修订', 0, 2**53 - 1)


def require_revision(span, revision):
    if span['revision'] != revision:
        raise Problem('光段修订已更新，请刷新后重新核对', 409)


def select(connection, span_id, raw):
    fields(raw, 'revision', *DIRECTIONS)
    span = find_span(connection, span_id)
    require_revision(span, revision_from(raw['revision']))
    current = selected(connection, span_id)
    wanted = {}
    for side in DIRECTIONS:
        if raw[side] is None:
            wanted[side] = None
            continue
        trace_id = key(raw[side], '凭证编号')
        trace = get_trace(connection, span_id, trace_id)['trace']
        if trace['direction'] != side:
            raise Problem('测量凭证方向与采用位置不一致')
        wanted[side] = trace_id
    ids = {side: receipt['trace']['trace_id'] if receipt else None for side, receipt in current.items()}
    if wanted == ids:
        return {'revision': span['revision'], 'selection': ids}
    for side, trace_id in wanted.items():
        if trace_id is None:
            connection.execute('DELETE FROM active_traces WHERE span_id = ? AND direction = ?', (span_id, side))
        else:
            connection.execute('INSERT INTO active_traces VALUES (?, ?, ?) '
                               'ON CONFLICT(span_id, direction) DO UPDATE SET trace_id = excluded.trace_id',
                               (span_id, side, trace_id))
    connection.execute('UPDATE spans SET revision = revision + 1 WHERE span_id = ?', (span_id,))
    return {'revision': span['revision'] + 1, 'selection': wanted}
