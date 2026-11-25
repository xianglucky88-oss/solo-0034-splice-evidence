"""整路验收的冻结导出。"""

import csv
from io import StringIO


def _label(port):
    return f"{port['box']}/{port['port']}"


def route_csv(release):
    target = StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(['route_id', 'snapshot_sha256', 'part', 'order', 'ref', 'start_mm', 'end_mm',
                     'forward_mdb', 'backward_mdb', 'estimate_x2_mdb'])
    snapshot = release['snapshot']
    digest = release['digest']
    for segment in snapshot['segments']:
        if segment['order'] is None:
            continue
        writer.writerow([snapshot['route_id'], digest, 'segment', segment['order'], segment['span_id'],
                         segment['start_mm'], segment['end_mm'], segment['forward_mdb'],
                         segment['backward_mdb'], segment['estimate_x2_mdb']])
    for bridge in snapshot['bridges']:
        if bridge['order'] is None:
            continue
        writer.writerow([snapshot['route_id'], digest, 'bridge', bridge['order'],
                         f"{_label(bridge['from'])}>{_label(bridge['to'])}",
                         bridge['start_mm'], bridge['end_mm'], bridge['forward_mdb'],
                         bridge['backward_mdb'], 2 * bridge['estimate_mdb']])
    budget = snapshot['budget']
    writer.writerow([snapshot['route_id'], digest, 'total', '', '', '', '', budget['measured_a_mdb'],
                     budget['measured_b_mdb'], budget['estimate_x2_mdb']])
    return target.getvalue().encode('utf-8')
