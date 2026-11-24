from .codec import pack, unpack
from .errors import Problem
from .plan import plan_from


def find_span(connection, span_id):
    row = connection.execute('SELECT plan, revision FROM spans WHERE span_id = ?', (span_id,)).fetchone()
    if row is None:
        raise Problem('未找到该光段', 404)
    return {'plan': unpack(row['plan']), 'revision': row['revision']}


def create_span(connection, raw):
    plan = plan_from(raw)
    data = pack(plan)
    span_id = plan['span_id']
    row = connection.execute('SELECT plan FROM spans WHERE span_id = ?', (span_id,)).fetchone()
    if row is None:
        connection.execute('INSERT INTO spans(span_id, plan) VALUES (?, ?)', (span_id, data))
    elif row['plan'] != data:
        raise Problem('光段编号已经绑定其他计划', 409)
    return find_span(connection, span_id)


def list_spans(connection):
    return [{'span_id': row['span_id'], 'revision': row['revision'], 'label': unpack(row['plan'])['label']}
            for row in connection.execute('SELECT * FROM spans ORDER BY span_id')]
