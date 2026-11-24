from .codec import digest, pack, unpack
from .errors import Problem
from .selection import require_revision, revision_from
from .spans import find_span
from .values import fields
from .workbench import workspace


def list_releases(connection, span_id):
    find_span(connection, span_id)
    return [dict(row) for row in connection.execute(
        'SELECT revision, digest FROM releases WHERE span_id = ? ORDER BY revision DESC', (span_id,))]


def get_release(connection, span_id, revision):
    row = connection.execute('SELECT digest, payload FROM releases WHERE span_id = ? AND revision = ?',
                             (span_id, revision)).fetchone()
    if row is None:
        raise Problem('未找到该签发版本', 404)
    return {'digest': row['digest'], 'snapshot': unpack(row['payload'])}


def issue(connection, span_id, raw):
    revision = revision_from(fields(raw, 'revision')['revision'])
    span = find_span(connection, span_id)
    require_revision(span, revision)
    existing = connection.execute('SELECT 1 FROM releases WHERE span_id = ? AND revision = ?',
                                  (span_id, revision)).fetchone()
    if existing:
        return get_release(connection, span_id, revision)
    snapshot = workspace(connection, span_id)
    if snapshot['budget']['status'] != 'ready':
        raise Problem('当前修订仍有留置项，无法签发', 409)
    data = pack(snapshot)
    sha = digest(data)
    connection.execute('INSERT INTO releases VALUES (?, ?, ?, ?)', (span_id, revision, sha, data))
    return {'digest': sha, 'snapshot': snapshot}
