import csv
from io import StringIO


def _side(release, side):
    adopted = {item['side']: item for item in release.get('handoff', {}).get('adopted', [])}
    meta = (release['snapshot'].get('active') or {}).get(side) or {}
    source = adopted.get(side) or meta
    if source.get('source', 'unstated') != 'stated':
        return ['unstated', '', '', '']
    notice = source.get('notice') or {}
    return ['stated', source.get('instrument_id') or '', source.get('calibration_batch') or '', notice.get('notice_id', '')]


def site_csv(release):
    target = StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'site_id', 'design_mm', 'mean_x2_mdb',
                     'limit_mdb', 'a_trace', 'a_event', 'b_trace', 'b_event',
                     'a_source', 'a_instrument', 'a_batch', 'a_notice',
                     'b_source', 'b_instrument', 'b_batch', 'b_notice',
                     'handoff_status'])
    snapshot = release['snapshot']
    handoff = release.get('handoff') or {'status': 'clear', 'affected': []}
    for site in snapshot['sites']:
        a, b = (site['observations'][side] for side in ('a', 'b'))
        writer.writerow([snapshot['plan']['span_id'], snapshot['revision'], release['digest'], site['site_id'],
                         site['at_mm'], site['mean_x2_mdb'], site['limit_mdb'],
                         a['trace_id'], a['event_id'], b['trace_id'], b['event_id'],
                         *_side(release, 'a'), *_side(release, 'b'), handoff['status']])
    return target.getvalue().encode('utf-8')
