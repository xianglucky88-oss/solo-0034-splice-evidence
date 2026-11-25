from .errors import Problem
from .plan_versions import version_plan
from .selection import require_revision, revision_from
from .spans import find_span
from .trace import DIRECTIONS
from .values import fields, key
from .version_receipts import get_version_trace


def version_selected(connection, span_id, plan_version):
    slots = dict.fromkeys(DIRECTIONS)
    for row in connection.execute(
            'SELECT direction, trace_id FROM version_active WHERE span_id = ? AND plan_version = ?',
            (span_id, plan_version)):
        slots[row['direction']] = get_version_trace(connection, span_id, plan_version, row['trace_id'])
    return slots


def select_version(connection, span_id, plan_version, raw):
    fields(raw, 'revision', *DIRECTIONS)
    version_plan(connection, span_id, plan_version)
    span = find_span(connection, span_id)
    require_revision(span, revision_from(raw['revision']))
    current = version_selected(connection, span_id, plan_version)
    wanted = {}
    for side in DIRECTIONS:
        if raw[side] is None:
            wanted[side] = None
            continue
        trace_id = key(raw[side], '凭证编号')
        trace = get_version_trace(connection, span_id, plan_version, trace_id)['trace']
        if trace['direction'] != side:
            raise Problem('测量凭证方向与采用位置不一致')
        wanted[side] = trace_id
    current_ids = {side: item['trace']['trace_id'] if item else None for side, item in current.items()}
    if wanted == current_ids:
        return {'revision': span['revision'], 'plan_version': plan_version, 'selection': wanted}
    for side, trace_id in wanted.items():
        connection.execute('DELETE FROM version_active WHERE span_id = ? AND plan_version = ? AND direction = ?',
                           (span_id, plan_version, side))
        if trace_id is not None:
            connection.execute('INSERT INTO version_active VALUES (?, ?, ?, ?)',
                               (span_id, plan_version, side, trace_id))
    connection.execute('UPDATE spans SET revision = revision + 1 WHERE span_id = ?', (span_id,))
    return {'revision': span['revision'] + 1, 'plan_version': plan_version, 'selection': wanted}
