"""路由拼装计划登记与整路验收快照。"""

from .codec import digest, pack, unpack
from .errors import Problem
from .values import fields
from .whole_route import assemble, route_plan_from


def find_route(connection, route_id):
    row = connection.execute('SELECT plan FROM routes WHERE route_id = ?', (route_id,)).fetchone()
    if row is None:
        raise Problem('未找到该整路路由', 404)
    return {'plan': unpack(row['plan'])}


def create_route(connection, raw):
    plan = route_plan_from(raw)
    data = pack(plan)
    route_id = plan['route_id']
    row = connection.execute('SELECT plan FROM routes WHERE route_id = ?', (route_id,)).fetchone()
    if row is None:
        connection.execute('INSERT INTO routes(route_id, plan) VALUES (?, ?)', (route_id, data))
    elif row['plan'] != data:
        raise Problem('路由编号已经绑定其他拼装计划', 409)
    return find_route(connection, route_id)


def list_routes(connection):
    return [{'route_id': row['route_id'], 'label': unpack(row['plan'])['label']}
            for row in connection.execute('SELECT * FROM routes ORDER BY route_id')]


def route_workspace(connection, route_id):
    return assemble(connection, find_route(connection, route_id))


def list_route_releases(connection, route_id):
    find_route(connection, route_id)
    return [dict(row) for row in connection.execute(
        'SELECT digest, sequence FROM route_releases WHERE route_id = ? ORDER BY sequence DESC', (route_id,))]


def get_route_release(connection, route_id, sha):
    row = connection.execute('SELECT payload FROM route_releases WHERE route_id = ? AND digest = ?',
                             (route_id, sha)).fetchone()
    if row is None:
        raise Problem('未找到该整路验收记录', 404)
    return {'digest': sha, 'snapshot': unpack(row['payload'])}


def issue_route(connection, route_id, raw):
    fields(raw)
    snapshot = assemble(connection, find_route(connection, route_id))
    if snapshot['budget']['status'] != 'ready':
        raise Problem('整路仍有留置项，无法验收', 409)
    data = pack(snapshot)
    sha = digest(data)
    row = connection.execute('SELECT 1 FROM route_releases WHERE route_id = ? AND digest = ?',
                             (route_id, sha)).fetchone()
    if row is None:
        sequence = connection.execute('SELECT COALESCE(MAX(sequence), 0) + 1 FROM route_releases WHERE route_id = ?',
                                      (route_id,)).fetchone()[0]
        connection.execute('INSERT INTO route_releases VALUES (?, ?, ?, ?)', (route_id, sha, sequence, data))
    return {'digest': sha, 'snapshot': snapshot}
