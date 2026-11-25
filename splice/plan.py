from .errors import Problem
from .values import fields, integer, key, rows, text

MAX_DISTANCE = 1_000_000_000
MAX_LOSS = 1_000_000


def plan_from(raw):
    value = fields(raw, 'span_id', 'label', 'a_label', 'b_label', 'length_mm', 'fixed_mdb',
                   'link_limit_mdb', 'residual_limit_mdb', 'sites', optional=('marks_mm',))
    length = integer(value['length_mm'], '光段长度', 2, MAX_DISTANCE)
    marks = []
    if 'marks_mm' in value:
        for raw_mark in rows(value['marks_mm'], '中间标记', 0, 500):
            mark = integer(raw_mark, '中间标记实地里程', 1, length - 1)
            if mark in marks:
                raise Problem('中间标记实地里程必须唯一')
            marks.append(mark)
        marks.sort()
    sites = []
    ids = set()
    positions = set()
    for raw_site in rows(value['sites'], '接续点', 1, 500):
        site = fields(raw_site, 'site_id', 'at_mm', 'window_mm', 'limit_mdb')
        site_id = key(site['site_id'], '接续点编号')
        position = integer(site['at_mm'], '接续点里程', 1, length - 1)
        window = integer(site['window_mm'], '归点窗口', 0, length)
        limit = integer(site['limit_mdb'], '接续点限值', 0, MAX_LOSS)
        if site_id in ids or position in positions:
            raise Problem('接续点编号和设计里程各自必须唯一')
        ids.add(site_id)
        positions.add(position)
        sites.append({'site_id': site_id, 'at_mm': position, 'window_mm': window, 'limit_mdb': limit})
    result = {
        'span_id': key(value['span_id'], '光段编号'),
        'label': text(value['label'], '光段名称'),
        'a_label': text(value['a_label'], '甲端名称'),
        'b_label': text(value['b_label'], '乙端名称'),
        'length_mm': length,
        'fixed_mdb': integer(value['fixed_mdb'], '固定损耗', 0, MAX_LOSS),
        'link_limit_mdb': integer(value['link_limit_mdb'], '链路限值', 0, MAX_LOSS),
        'residual_limit_mdb': integer(value['residual_limit_mdb'], '闭合差限值', 0, MAX_LOSS),
        'marks_mm': marks,
        'sites': sorted(sites, key=lambda site: site['at_mm']),
    }
    if not marks:
        # Keep plans without intermediate marks byte-identical to the original
        # encoding so receipts and releases remain reproducible.
        del result['marks_mm']
    return result
