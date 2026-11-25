from .codec import pack, unpack
from .errors import Problem
from .plan import plan_from
from .relations import relations_from
from .selection import require_revision, revision_from
from .spans import find_span
from .values import fields


def latest_version(connection, span_id):
    row = connection.execute('SELECT MAX(plan_version) AS version FROM plan_versions WHERE span_id = ?',
                             (span_id,)).fetchone()
    return row['version'] if row['version'] is not None else 1


def version_plan(connection, span_id, plan_version):
    if plan_version == 1:
        return find_span(connection, span_id)['plan']
    row = connection.execute('SELECT plan FROM plan_versions WHERE span_id = ? AND plan_version = ?',
                             (span_id, plan_version)).fetchone()
    if row is None:
        raise Problem('未找到该计划版本', 404)
    return unpack(row['plan'])


def activate_version(connection, span_id, raw):
    fields(raw, 'revision', 'plan', 'basis', 'relations')
    span = find_span(connection, span_id)
    require_revision(span, revision_from(raw['revision']))
    parent_version = latest_version(connection, span_id)
    parent_plan = version_plan(connection, span_id, parent_version)
    plan = plan_from(raw['plan'])
    if plan['span_id'] != span_id:
        raise Problem('换版计划必须沿用原光段编号')
    basis, relations = relations_from({'basis': raw['basis'], 'relations': raw['relations']},
                                      parent_plan, plan)
    new_version = parent_version + 1
    connection.execute('INSERT INTO plan_versions(span_id, plan_version, parent_version, basis, plan) '
                       'VALUES (?, ?, ?, ?, ?)',
                       (span_id, new_version, parent_version, basis, pack(plan)))
    for item in relations:
        from_sites = item['from_sites'] or [None]
        to_sites = item['to_sites'] or [None]
        for from_site in from_sites:
            for to_site in to_sites:
                connection.execute(
                    'INSERT INTO plan_relations(span_id, parent_version, plan_version, relation, from_site, to_site) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (span_id, parent_version, new_version, item['relation'], from_site, to_site))
    connection.execute('UPDATE spans SET revision = revision + 1 WHERE span_id = ?', (span_id,))
    return {'span_id': span_id, 'plan_version': new_version, 'parent_version': parent_version,
            'revision': span['revision'] + 1, 'basis': basis, 'relations': relations, 'plan': plan}


def list_versions(connection, span_id):
    find_span(connection, span_id)
    result = [{'plan_version': 1, 'parent_version': None, 'basis': '初始登记计划'}]
    for row in connection.execute(
            'SELECT plan_version, parent_version, basis FROM plan_versions WHERE span_id = ? ORDER BY plan_version',
            (span_id,)):
        result.append({'plan_version': row['plan_version'], 'parent_version': row['parent_version'],
                       'basis': row['basis']})
    return result


def list_relations(connection, span_id, plan_version):
    find_span(connection, span_id)
    groups = {}
    order = []
    for row in connection.execute(
            'SELECT relation, from_site, to_site FROM plan_relations '
            'WHERE span_id = ? AND plan_version = ? ORDER BY rowid', (span_id, plan_version)):
        key = row['relation']
        group = groups.setdefault(key, {'relation': key, 'from_sites': [], 'to_sites': []})
        if key not in order:
            order.append(key)
        if row['from_site'] is not None and row['from_site'] not in group['from_sites']:
            group['from_sites'].append(row['from_site'])
        if row['to_site'] is not None and row['to_site'] not in group['to_sites']:
            group['to_sites'].append(row['to_site'])
    return [groups[key] for key in order]
