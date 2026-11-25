from .errors import Problem
from .measure import UNITS, canonical_number, loss_fraction
from .plan import MAX_DISTANCE, MAX_LOSS
from .values import fields, integer, key, rows

DIRECTIONS = ('a', 'b')


def _loss(raw, mdb_field, db_field, label):
    keys = raw.keys()
    has_mdb, has_db = mdb_field in keys, db_field in keys
    if has_mdb == has_db:
        raise Problem(f'{label} 必须且只能提供 {mdb_field} 或 {db_field} 之一')
    if has_mdb:
        return mdb_field, loss_fraction(raw[mdb_field], 'mdb', label)
    return db_field, loss_fraction(raw[db_field], 'db', label)


def trace_from(value):
    fields(value, 'trace_id', 'direction', 'near_mm', 'far_mm', 'total_unit',
           *{key for key in ('total_mdb', 'total_db') if key in value}, 'events')
    if value['total_unit'] not in UNITS:
        raise Problem('实测总损耗单位必须为 db 或 mdb')
    near = integer(value['near_mm'], '近端标记', 0, MAX_DISTANCE - 1)
    far = integer(value['far_mm'], '远端标记', near + 1, MAX_DISTANCE)
    if value['direction'] not in DIRECTIONS:
        raise Problem('测量方向必须为 a 或 b')
    total_field, total = _loss(value, 'total_mdb', 'total_db', '实测总损耗')
    if total < 0 or total > MAX_LOSS:
        raise Problem(f'实测总损耗必须为 0 至 {MAX_LOSS} 毫分贝')
    events = []
    writing_events = []
    existing = set()
    for raw in rows(value['events'], '测量事件', 0, 2000):
        fields(raw, 'event_id', 'at_mm', 'loss_unit',
               *{key for key in ('loss_mdb', 'loss_db') if key in raw})
        if raw['loss_unit'] not in UNITS:
            raise Problem('事件损耗单位必须为 db 或 mdb')
        event_id = key(raw['event_id'], '事件编号')
        if event_id in existing:
            raise Problem(f'同一凭证内事件编号重复：{event_id}')
        existing.add(event_id)
        at = integer(raw['at_mm'], '仪表里程', 0, MAX_DISTANCE)
        loss_field, loss = _loss(raw, 'loss_mdb', 'loss_db', '有符号事件损耗')
        if loss < -MAX_LOSS or loss > MAX_LOSS:
            raise Problem(f'有符号事件损耗必须为 -{MAX_LOSS} 至 {MAX_LOSS} 毫分贝')
        events.append({'event_id': event_id, 'at_mm': at, 'loss_mdb': canonical_number(loss)})
        writing_events.append({'event_id': event_id, 'at_mm': at, 'loss_unit': raw['loss_unit'],
                               loss_field: raw[loss_field]})
    trace = {'trace_id': key(value['trace_id'], '凭证编号'), 'direction': value['direction'],
             'near_mm': near, 'far_mm': far, 'total_mdb': canonical_number(total), 'events': events}
    writing = {'trace_id': value['trace_id'], 'direction': value['direction'],
               'near_mm': near, 'far_mm': far, 'total_unit': value['total_unit'],
               total_field: value[total_field], 'events': writing_events}
    return trace, writing
