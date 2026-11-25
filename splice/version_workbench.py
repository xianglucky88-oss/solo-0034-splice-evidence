from .codec import digest, pack, unpack
from .errors import Problem
from .plan_versions import version_plan
from .projection import evaluate
from .selection import require_revision, revision_from
from .spans import find_span
from .values import fields
from .version_selection import version_selected


def version_workspace(connection, span_id, plan_version):
    plan = version_plan(connection, span_id, plan_version)
    span = find_span(connection, span_id)
    slots = version_selected(connection, span_id, plan_version)
    traces = [item['trace'] for item in slots.values() if item]
    metadata = {side: {'trace_id': item['trace']['trace_id'], 'digest': item['digest']} if item else None
                for side, item in slots.items()}
    projection = evaluate({'revision': span['revision'], 'plan': plan}, metadata, traces)
    projection['plan_version'] = plan_version
    return projection


def list_version_releases(connection, span_id, plan_version):
    version_plan(connection, span_id, plan_version)
    return [{'revision': row['revision'], 'digest': row['digest'], 'plan_version': plan_version}
            for row in connection.execute(
                'SELECT revision, digest FROM version_releases WHERE span_id = ? AND plan_version = ? '
                'ORDER BY revision DESC', (span_id, plan_version))]


def get_version_release(connection, span_id, plan_version, revision):
    row = connection.execute(
        'SELECT digest, payload FROM version_releases WHERE span_id = ? AND plan_version = ? AND revision = ?',
        (span_id, plan_version, revision)).fetchone()
    if row is None:
        raise Problem('未找到该签发版本', 404)
    return {'digest': row['digest'], 'snapshot': unpack(row['payload'])}


def issue_version(connection, span_id, plan_version, raw):
    revision = revision_from(fields(raw, 'revision')['revision'])
    span = find_span(connection, span_id)
    require_revision(span, revision)
    existing = connection.execute(
        'SELECT 1 FROM version_releases WHERE span_id = ? AND plan_version = ? AND revision = ?',
        (span_id, plan_version, revision)).fetchone()
    if existing:
        return get_version_release(connection, span_id, plan_version, revision)
    snapshot = version_workspace(connection, span_id, plan_version)
    if snapshot['budget']['status'] != 'ready':
        raise Problem('当前修订仍有留置项，无法签发', 409)
    data = pack(snapshot)
    sha = digest(data)
    connection.execute('INSERT INTO version_releases VALUES (?, ?, ?, ?, ?)',
                       (span_id, plan_version, revision, sha, data))
    return {'digest': sha, 'snapshot': snapshot}
