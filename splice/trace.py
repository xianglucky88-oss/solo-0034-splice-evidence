from .errors import Problem
from .plan import MAX_DISTANCE, MAX_LOSS
from .values import fields, integer, key, rows

DIRECTIONS = ('a', 'b')


def trace_from(value):
    fields(value, 'trace_id', 'direction', 'near_mm', 'far_mm', 'total_mdb', 'events')
    near = integer(value['near_mm'], '近端标记', 0, MAX_DISTANCE - 1)
    far = integer(value['far_mm'], '远端标记', near + 1, MAX_DISTANCE)
    if value['direction'] not in DIRECTIONS:
        raise Problem('测量方向必须为 a 或 b')
    events = []
    existing = set()
    for raw in rows(value['events'], '测量事件', 0, 2000):
        row = fields(raw, 'event_id', 'at_mm', 'loss_mdb')
        event_id = key(row['event_id'], '事件编号')
        if event_id in existing:
            raise Problem(f'同一凭证内事件编号重复：{event_id}')
        existing.add(event_id)
        events.append({
            'event_id': event_id, 'at_mm': integer(row['at_mm'], '仪表里程', 0, MAX_DISTANCE),
            'loss_mdb': integer(row['loss_mdb'], '有符号事件损耗', -MAX_LOSS, MAX_LOSS),
        })
    return {'trace_id': key(value['trace_id'], '凭证编号'), 'direction': value['direction'],
            'near_mm': near, 'far_mm': far,
            'total_mdb': integer(value['total_mdb'], '实测总损耗', 0, MAX_LOSS), 'events': events}
