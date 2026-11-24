from .codec import digest, pack, unpack
from .errors import Problem
from .spans import find_span
from .trace import trace_from


def receive(connection, span_id, raw):
    find_span(connection, span_id)
    trace = trace_from(raw)
    data = pack(trace)
    sha = digest(data)
    old = connection.execute('SELECT digest FROM traces WHERE span_id = ? AND trace_id = ?',
                             (span_id, trace['trace_id'])).fetchone()
    if old is not None and old['digest'] != sha:
        raise Problem('凭证编号已经绑定其他测量内容', 409)
    if old is None:
        connection.execute('INSERT INTO traces VALUES (?, ?, ?, ?, ?)',
                           (span_id, trace['trace_id'], trace['direction'], sha, data))
    return {'trace_id': trace['trace_id'], 'direction': trace['direction'], 'digest': sha, 'replayed': old is not None}


def get_trace(connection, span_id, trace_id):
    row = connection.execute('SELECT payload, digest FROM traces WHERE span_id = ? AND trace_id = ?',
                             (span_id, trace_id)).fetchone()
    if row is None:
        raise Problem('未找到该测量凭证', 404)
    return {'trace': unpack(row['payload']), 'digest': row['digest']}


def list_traces(connection, span_id):
    find_span(connection, span_id)
    return [dict(row) for row in connection.execute(
        'SELECT trace_id, direction, digest FROM traces WHERE span_id = ? ORDER BY direction, trace_id', (span_id,))]
