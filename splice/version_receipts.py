from .codec import digest, pack, unpack
from .errors import Problem
from .plan_versions import version_plan
from .trace import trace_from


def _known_digests(connection, span_id, plan_version):
    # 首版扫测存于旧表 traces；其后各版存于 version_traces。新版拒收任何迟到旧扫测。
    legacy = {row['digest'] for row in connection.execute(
        'SELECT digest FROM traces WHERE span_id = ?', (span_id,))}
    if plan_version <= 2:
        return legacy
    earlier = {row['digest'] for row in connection.execute(
        'SELECT digest FROM version_traces WHERE span_id = ? AND plan_version < ?',
        (span_id, plan_version))}
    return legacy | earlier


def receive_version_trace(connection, span_id, plan_version, raw):
    version_plan(connection, span_id, plan_version)
    trace = trace_from(raw)
    data = pack(trace)
    sha = digest(data)
    if sha in _known_digests(connection, span_id, plan_version):
        raise Problem('新版仅采用新版双向扫测，迟到的旧扫测不能在新版收件', 409)
    old = connection.execute(
        'SELECT digest FROM version_traces WHERE span_id = ? AND plan_version = ? AND trace_id = ?',
        (span_id, plan_version, trace['trace_id'])).fetchone()
    if old is not None and old['digest'] != sha:
        raise Problem('凭证编号已经绑定其他测量内容', 409)
    if old is None:
        connection.execute('INSERT INTO version_traces(span_id, plan_version, trace_id, direction, digest, payload) '
                           'VALUES (?, ?, ?, ?, ?, ?)',
                           (span_id, plan_version, trace['trace_id'], trace['direction'], sha, data))
    return {'trace_id': trace['trace_id'], 'direction': trace['direction'], 'digest': sha,
            'plan_version': plan_version, 'replayed': old is not None}


def get_version_trace(connection, span_id, plan_version, trace_id):
    row = connection.execute(
        'SELECT payload, digest FROM version_traces WHERE span_id = ? AND plan_version = ? AND trace_id = ?',
        (span_id, plan_version, trace_id)).fetchone()
    if row is None:
        raise Problem('未找到该测量凭证', 404)
    return {'trace': unpack(row['payload']), 'digest': row['digest']}


def list_version_traces(connection, span_id, plan_version):
    version_plan(connection, span_id, plan_version)
    return [{'trace_id': row['trace_id'], 'direction': row['direction'], 'digest': row['digest']}
            for row in connection.execute(
                'SELECT trace_id, direction, digest FROM version_traces '
                'WHERE span_id = ? AND plan_version = ? ORDER BY direction, trace_id',
                (span_id, plan_version))]
