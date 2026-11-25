from .codec import digest, pack, unpack
from .errors import Problem
from .revocations import assess_release
from .selection import require_revision, revision_from
from .spans import find_span
from .values import fields
from .workbench import workspace


def _frozen(snapshot):
    """冻结核算法结果；交接状态按回读时刻重新核对。"""
    return {key: value for key, value in snapshot.items() if key != 'handoff'}


def _release(connection, span_id, revision, digest_value, snapshot):
    return {'revision': revision, 'digest': digest_value, 'snapshot': snapshot,
            'handoff': assess_release(connection, span_id, snapshot)}


def list_releases(connection, span_id):
    find_span(connection, span_id)
    items = []
    for row in connection.execute(
            'SELECT revision, digest, payload FROM releases WHERE span_id = ? ORDER BY revision DESC', (span_id,)):
        snapshot = unpack(row['payload'])
        items.append({'revision': row['revision'], 'digest': row['digest'],
                      'handoff': assess_release(connection, span_id, snapshot)})
    return items


def get_snapshot(connection, span_id, revision):
    row = connection.execute('SELECT digest, payload FROM releases WHERE span_id = ? AND revision = ?',
                             (span_id, revision)).fetchone()
    if row is None:
        raise Problem('未找到该签发版本', 404)
    return {'digest': row['digest'], 'snapshot': unpack(row['payload'])}


def get_release(connection, span_id, revision):
    frozen = get_snapshot(connection, span_id, revision)
    return _release(connection, span_id, revision, frozen['digest'], frozen['snapshot'])


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
        if snapshot['handoff']['status'] != 'clear':
            raise Problem('所采用的校验批次已撤销，不能签发', 409)
        raise Problem('当前修订仍有留置项，无法签发', 409)
    frozen = _frozen(snapshot)
    data = pack(frozen)
    sha = digest(data)
    connection.execute('INSERT INTO releases VALUES (?, ?, ?, ?)', (span_id, revision, sha, data))
    return _release(connection, span_id, revision, sha, frozen)
