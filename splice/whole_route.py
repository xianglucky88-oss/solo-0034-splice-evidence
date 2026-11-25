"""把已签光段按实物端口拼成一条整路，并在整路边界上核算链路与闭合差。

各段以本段两端端口为测量边界；相邻段之间必须有认可桥接。整路只引用
各段的已签修订，签发后不再随分段再次签发而改变。
"""

from collections import defaultdict

from .errors import Problem
from .plan import MAX_DISTANCE, MAX_LOSS
from .ports import port_from, port_key, port_label
from .releases import get_release
from .selection import revision_from
from .values import fields, integer, key, rows, text

RULESET = 'splice-route-v1'
ORIENTATIONS = ('forward', 'reverse')


def _canonical_bridge(record):
    return (port_key(record['from']), port_key(record['to']), record['gap_mm'],
            record['forward_mdb'], record['backward_mdb'], record['estimate_mdb'])


def route_plan_from(raw):
    value = fields(raw, 'route_id', 'label', 'start', 'end', 'link_limit_mdb',
                   'residual_limit_mdb', 'segments', 'bridges')
    start = port_from(value['start'], '起点')
    end = port_from(value['end'], '终点')
    segments = []
    for raw_segment in rows(value['segments'], '光段引用', 1, 200):
        segment = fields(raw_segment, 'span_id', 'revision', 'entry', 'exit', 'orientation')
        if segment['orientation'] not in ORIENTATIONS:
            raise Problem('光段朝向必须为 forward 或 reverse')
        segments.append({
            'span_id': key(segment['span_id'], '光段编号'),
            'revision': revision_from(segment['revision']),
            'entry': port_from(segment['entry'], '入端'),
            'exit': port_from(segment['exit'], '出端'),
            'orientation': segment['orientation'],
        })
    bridges = []
    for raw_bridge in rows(value['bridges'], '桥接记录', 0, 199):
        bridge = fields(raw_bridge, 'from', 'to', 'gap_mm', 'forward_mdb', 'backward_mdb', 'estimate_mdb')
        record = {
            'from': port_from(bridge['from'], '桥接起端'),
            'to': port_from(bridge['to'], '桥接止端'),
            'gap_mm': integer(bridge['gap_mm'], '端口参考面间距', 0, MAX_DISTANCE),
            'forward_mdb': integer(bridge['forward_mdb'], '桥接正向实测', 0, MAX_LOSS),
            'backward_mdb': integer(bridge['backward_mdb'], '桥接反向实测', 0, MAX_LOSS),
            'estimate_mdb': integer(bridge['estimate_mdb'], '桥接估算损耗', 0, MAX_LOSS),
        }
        if port_key(record['from']) == port_key(record['to']):
            raise Problem('桥接两端不能是同一实物端口')
        bridges.append(record)
    segments.sort(key=lambda item: (item['span_id'], item['revision'], port_key(item['entry']),
                                    port_key(item['exit']), item['orientation']))
    bridges.sort(key=_canonical_bridge)
    return {
        'route_id': key(value['route_id'], '路由编号'),
        'label': text(value['label'], '路由名称'),
        'start': start,
        'end': end,
        'link_limit_mdb': integer(value['link_limit_mdb'], '整路链路限值', 0, MAX_LOSS),
        'residual_limit_mdb': integer(value['residual_limit_mdb'], '整路闭合差限值', 0, MAX_LOSS),
        'segments': segments,
        'bridges': bridges,
    }


def _issue(issues, code, detail):
    if not any(item['code'] == code and item['detail'] == detail for item in issues):
        issues.append({'code': code, 'detail': detail})


def _segment_stamp(segment):
    return (segment['revision'], port_key(segment['entry']), port_key(segment['exit']),
            segment['orientation'])


def _bridge_mirror(record):
    return (port_key(record['to']), port_key(record['from']), record['gap_mm'],
            record['backward_mdb'], record['forward_mdb'], record['estimate_mdb'])


def _unique_segments(plan, issues):
    """每段恰用一次：同名光段的重复引用只保留一份，引用互相矛盾时留置。"""
    ordered = defaultdict(list)
    for segment in plan['segments']:
        ordered[segment['span_id']].append(segment)
    unique = []
    conflicted = set()
    for span_id, items in ordered.items():
        stamps = {_segment_stamp(item) for item in items}
        if len(stamps) > 1:
            conflicted.add(span_id)
            _issue(issues, 'conflicting_segment',
                   f"光段 {span_id} 被以不同修订、端口或朝向重复引用")
            continue
        unique.append({'record_count': len(items), **items[0]})
    return unique, conflicted


def _unique_bridges(plan, issues):
    """同一实物连接的重复记录只计一次；正反向重记视为同一条，异内容留置。"""
    unique = []
    chosen = {}
    for index, bridge in enumerate(plan['bridges']):
        pair = frozenset((port_key(bridge['from']), port_key(bridge['to'])))
        previous = chosen.get(pair)
        if previous is None:
            entry = {'record_count': 1, 'plan_order': index + 1, 'record': bridge}
            chosen[pair] = entry
            unique.append(entry)
        elif _canonical_bridge(previous['record']) == _canonical_bridge(bridge) or \
                _bridge_mirror(previous['record']) == _canonical_bridge(bridge):
            previous['record_count'] += 1
        else:
            _issue(issues, 'conflicting_bridge',
                   f"端口 {port_label(bridge['from'])} 与 {port_label(bridge['to'])} 之间的桥接记录互相矛盾")
    return unique


def _assemble(plan, segments, bridges, issues):
    """从交接组指定的起点走唯一一条经过每段恰一次的甲端至乙端链。"""
    start = port_key(plan['start'])
    end = port_key(plan['end'])
    if start == end:
        _issue(issues, 'unknown_port', '整路起点与终点不能是同一实物端口')
        return None

    entries = defaultdict(list)
    exits = defaultdict(list)
    for index, segment in enumerate(segments):
        entry = port_key(segment['entry'])
        leave = port_key(segment['exit'])
        if entry == leave:
            _issue(issues, 'unknown_port', f"光段 {segment['span_id']} 的入端与出端是同一实物端口")
            return None
        entries[entry].append(index)
        exits[leave].append(index)
    if any(len(items) > 1 for items in entries.values()):
        _issue(issues, 'ambiguous_assembly', '同一实物端口被多个光段作为入端，拼接不唯一')
        return None
    if any(len(items) > 1 for items in exits.values()):
        _issue(issues, 'ambiguous_assembly', '同一实物端口被多个光段作为出端，拼接不唯一')
        return None
    if set(entries) & set(exits):
        _issue(issues, 'missing_bridge', '有实物端口直接同时作为光段的入端和出端，缺少认可桥接')
        return None
    if start not in entries:
        _issue(issues, 'unknown_port', f'整路起点 {port_label(plan["start"])} 不是任何光段的入端')
        return None
    if end not in exits:
        _issue(issues, 'unknown_port', f'整路终点 {port_label(plan["end"])} 不是任何光段的出端')
        return None

    bridges_at = defaultdict(list)
    for index, entry in enumerate(bridges):
        bridges_at[port_key(entry['record']['from'])].append(index)
        bridges_at[port_key(entry['record']['to'])].append(index)
    if any(len(items) > 1 for items in bridges_at.values()):
        _issue(issues, 'ambiguous_assembly', '同一实物端口接有多条桥接记录，拼接不唯一')
        return None

    sequence = []
    used_segments = set()
    used_bridges = set()
    position = start
    for _ in range(2 * (len(segments) + len(bridges)) + 2):
        segment_index = entries[position][0]
        if segment_index in used_segments:
            _issue(issues, 'ambiguous_assembly', '端口拼接重复经过同一光段，次序不唯一')
            return None
        used_segments.add(segment_index)
        segment = segments[segment_index]
        sequence.append(('segment', segment_index))
        position = port_key(segment['exit'])
        if position == end:
            break
        options = bridges_at.get(position, [])
        if not options:
            _issue(issues, 'missing_bridge',
                   f'光段 {segment["span_id"]} 出端 {port_label(segment["exit"])} 没有认可桥接')
            return None
        bridge_index = options[0]
        if bridge_index in used_bridges:
            _issue(issues, 'missing_bridge', '桥接记录不足以把链路引向新的实物端口')
            return None
        used_bridges.add(bridge_index)
        record = bridges[bridge_index]['record']
        upstream = port_key(segment['exit'])
        position = (port_key(record['to']) if port_key(record['from']) == upstream
                    else port_key(record['from']))
        sequence.append(('bridge', bridge_index))
        if position not in entries:
            _issue(issues, 'unknown_port', '桥接止端没有可接续光段的入端')
            return None
    else:
        _issue(issues, 'ambiguous_assembly', '端口拼接出现循环，无法在指定终点闭合')
        return None
    if position != end:
        _issue(issues, 'unknown_port', '拼接链没有停在交接组指定的终点')
        return None
    if len(used_segments) != len(segments):
        unused = [item['span_id'] for index, item in enumerate(segments) if index not in used_segments]
        _issue(issues, 'unused_segment', f'以下光段不在独特的甲端至乙端链上：{", ".join(unused)}')
        return None
    if len(used_bridges) != len(bridges):
        _issue(issues, 'unused_bridge', '存在不连接相邻光段的桥接记录')
        return None
    return sequence


def _load(connection, segments, issues):
    loaded = []
    for segment in segments:
        view = {'release_digest': None, 'snapshot': None, 'ready': False}
        try:
            release = get_release(connection, segment['span_id'], segment['revision'])
        except Problem:
            _issue(issues, 'missing_segment_release',
                   f"光段 {segment['span_id']} 修订 {segment['revision']} 尚未签发")
            loaded.append(view)
            continue
        view['release_digest'] = release['digest']
        view['snapshot'] = release['snapshot']
        view['ready'] = release['snapshot']['budget']['status'] == 'ready'
        if not view['ready']:
            _issue(issues, 'segment_not_ready',
                   f"光段 {segment['span_id']} 修订 {segment['revision']} 并未就绪")
        loaded.append(view)
    return loaded


def _site_view(site, segment, release, segment_order, offset):
    length = release['snapshot']['plan']['length_mm']
    reversed_segment = segment['orientation'] == 'reverse'
    along = length - site['at_mm'] if reversed_segment else site['at_mm']
    sides = (('a', 'b'), ('b', 'a')) if reversed_segment else (('a', 'a'), ('b', 'b'))
    observations = {}
    for source, route_side in sides:
        event = site['observations'][source]
        observations[route_side] = None if event is None else {**event, 'source_side': source}
    return {
        'order': None,
        'segment_order': segment_order,
        'span_id': segment['span_id'],
        'revision': segment['revision'],
        'release_digest': release['release_digest'],
        'site_id': site['site_id'],
        'source_at_mm': site['at_mm'],
        'at_mm': offset + along,
        'mean_x2_mdb': site['mean_x2_mdb'],
        'limit_mdb': site['limit_mdb'],
        'status': site['status'],
        'observations': observations,
    }


def _collect(plan, segments, loaded, bridges, sequence):
    complete = True
    segment_views = []
    bridge_views = []
    sites = []
    offset = 0
    segment_order = 0
    bridge_order = 0
    measured_a = measured_b = estimate = 0
    for kind, index in sequence:
        if kind == 'segment':
            segment = segments[index]
            release = loaded[index]
            snapshot = release['snapshot']
            segment_order += 1
            length = snapshot['plan']['length_mm'] if snapshot else None
            totals = snapshot['budget']['totals_mdb'] if snapshot else {}
            segment_estimate = snapshot['budget']['estimate_x2_mdb'] if snapshot else None
            forward = backward = None
            if (not release['ready'] or length is None or segment_estimate is None
                    or 'a' not in totals or 'b' not in totals):
                complete = False
            else:
                forward, backward = ((totals['b'], totals['a']) if segment['orientation'] == 'reverse'
                                     else (totals['a'], totals['b']))
                measured_a += forward
                measured_b += backward
                estimate += segment_estimate
            segment_views.append({
                'order': segment_order,
                'span_id': segment['span_id'],
                'revision': segment['revision'],
                'release_digest': release['release_digest'],
                'orientation': segment['orientation'],
                'entry': segment['entry'],
                'exit': segment['exit'],
                'record_count': segment['record_count'],
                'start_mm': offset,
                'end_mm': None if length is None else offset + length,
                'length_mm': length,
                'forward_mdb': forward,
                'backward_mdb': backward,
                'estimate_x2_mdb': segment_estimate,
                'site_count': len(snapshot['sites']) if snapshot else None,
                'ready': release['ready'],
            })
            if snapshot:
                for site in snapshot['sites']:
                    sites.append(_site_view(site, segment, release, segment_order, offset))
            if length is not None:
                offset += length
        else:
            entry = bridges[index]
            record = entry['record']
            upstream = port_key(segments[_segment_before(sequence, index)[1]]['exit'])
            reversed_bridge = port_key(record['from']) != upstream
            bridge_order += 1
            bridge_views.append({
                'order': bridge_order,
                'plan_order': entry['plan_order'],
                'record_count': entry['record_count'],
                'from': record['to'] if reversed_bridge else record['from'],
                'to': record['from'] if reversed_bridge else record['to'],
                'record_from': record['from'],
                'record_to': record['to'],
                'reversed': reversed_bridge,
                'gap_mm': record['gap_mm'],
                'forward_mdb': record['backward_mdb'] if reversed_bridge else record['forward_mdb'],
                'backward_mdb': record['forward_mdb'] if reversed_bridge else record['backward_mdb'],
                'estimate_mdb': record['estimate_mdb'],
                'start_mm': offset,
                'end_mm': offset + record['gap_mm'],
            })
            measured_a += bridge_views[-1]['forward_mdb']
            measured_b += bridge_views[-1]['backward_mdb']
            estimate += 2 * record['estimate_mdb']
            offset += record['gap_mm']
    sites.sort(key=lambda site: (site['segment_order'], site['at_mm']))
    for order, site in enumerate(sites, 1):
        site['order'] = order
    if not complete:
        measured_a = measured_b = estimate = None
    return measured_a, measured_b, estimate, offset, segment_views, bridge_views, sites


def _segment_before(sequence, bridge_index):
    for position, (kind, index) in enumerate(sequence):
        if kind == 'bridge' and index == bridge_index:
            return sequence[position - 1]
    raise LookupError(bridge_index)


def _fallback(segments, loaded, bridges):
    segment_views = [{
        'order': None, 'span_id': segment['span_id'], 'revision': segment['revision'],
        'release_digest': loaded[index]['release_digest'], 'orientation': segment['orientation'],
        'entry': segment['entry'], 'exit': segment['exit'], 'record_count': segment['record_count'],
        'start_mm': None, 'end_mm': None, 'length_mm': None, 'forward_mdb': None,
        'backward_mdb': None, 'estimate_x2_mdb': None, 'site_count': None,
        'ready': loaded[index]['ready'],
    } for index, segment in enumerate(segments)]
    bridge_views = [{
        'order': None, 'plan_order': entry['plan_order'], 'record_count': entry['record_count'],
        'from': entry['record']['from'], 'to': entry['record']['to'],
        'record_from': entry['record']['from'], 'record_to': entry['record']['to'], 'reversed': False,
        'gap_mm': entry['record']['gap_mm'], 'forward_mdb': entry['record']['forward_mdb'],
        'backward_mdb': entry['record']['backward_mdb'], 'estimate_mdb': entry['record']['estimate_mdb'],
        'start_mm': None, 'end_mm': None,
    } for entry in bridges]
    return segment_views, bridge_views


def assemble(connection, route):
    plan = route['plan']
    issues = []
    segments, conflicted = _unique_segments(plan, issues)
    bridges = _unique_bridges(plan, issues)
    loaded = _load(connection, segments, issues)
    sequence = None if conflicted else _assemble(plan, segments, bridges, issues)

    blockers = []

    def block(code):
        if code not in blockers:
            blockers.append(code)

    for issue in issues:
        block(issue['code'])
    if sequence is None:
        segment_views, bridge_views = _fallback(segments, loaded, bridges)
        sites = []
        measured_a = measured_b = estimate = total_length = None
    else:
        measured_a, measured_b, estimate, total_length, segment_views, bridge_views, sites = _collect(
            plan, segments, loaded, bridges, sequence)
        for site in sites:
            if site['status'] == 'over':
                block('site_over_limit')
            elif site['status'] != 'pass':
                block('incomplete_sites')

    measured_x2 = None if measured_a is None else measured_a + measured_b
    residual_x2 = None if measured_x2 is None or estimate is None else measured_x2 - estimate
    link_limit_x2 = 2 * plan['link_limit_mdb']
    if measured_x2 is not None and measured_x2 > link_limit_x2:
        block('link_over_limit')
        _issue(issues, 'link_over_limit', '整路双向实测均值超过链路限值')
    if estimate is not None and estimate > link_limit_x2:
        block('link_over_limit')
        _issue(issues, 'link_over_limit', '整路估算损耗超过链路限值')
    if residual_x2 is not None and abs(residual_x2) > 2 * plan['residual_limit_mdb']:
        block('closure_over_limit')
        _issue(issues, 'closure_over_limit', '整路实测均值与估算的闭合差超过限值')

    return {
        'ruleset': RULESET,
        'route_id': plan['route_id'],
        'label': plan['label'],
        'plan': plan,
        'segments': segment_views,
        'bridges': bridge_views,
        'sites': sites,
        'budget': {
            'status': 'held' if blockers else 'ready',
            'blockers': blockers,
            'issues': issues,
            'measured_a_mdb': measured_a,
            'measured_b_mdb': measured_b,
            'measured_x2_mdb': measured_x2,
            'estimate_x2_mdb': estimate,
            'residual_x2_mdb': residual_x2,
            'link_limit_mdb': plan['link_limit_mdb'],
            'residual_limit_mdb': plan['residual_limit_mdb'],
            'total_length_mm': total_length,
        },
    }
