import csv
from io import StringIO


def site_csv(release):
    target = StringIO(newline='')
    snapshot = release['snapshot']
    if snapshot['mode'] == 'review':
        return _review_csv(target, release)
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'site_id', 'design_mm', 'mean_x2_mdb',
                     'limit_mdb', 'a_trace', 'a_event', 'b_trace', 'b_event'])
    for site in snapshot['sites']:
        a, b = (site['observations'][side] for side in ('a', 'b'))
        writer.writerow([snapshot['plan']['span_id'], snapshot['revision'], release['digest'], site['site_id'],
                         site['at_mm'], site['mean_x2_mdb'], site['limit_mdb'],
                         a['trace_id'], a['event_id'], b['trace_id'], b['event_id']])
    return target.getvalue().encode('utf-8')


def _review_csv(target, release):
    snapshot = release['snapshot']
    review = snapshot['review']
    review_direction = snapshot['review_direction']
    counter_direction = review['counter_direction']
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'roster_trace_id', 'tolerance_mdb',
                     'site_id', 'design_mm', 'mean_x2_mdb', 'limit_mdb', 'status',
                     'review_event', 'counter_event', 'counter_trace',
                     'estimate_x2_mdb', 'measured_x2_mdb', 'residual_x2_mdb', 'member_blockers'])
    counter_id = snapshot['active'][counter_direction]['trace_id']
    plan = snapshot['plan']
    for trace_id in review['group']:
        member = review['members'][trace_id]
        for site in member['sites']:
            writer.writerow([plan['span_id'], snapshot['revision'], release['digest'], trace_id,
                             review['tolerance_mdb'], site['site_id'], site['at_mm'], site['mean_x2_mdb'],
                             site['limit_mdb'], site['status'], site['own_event_id'], site['counter_event_id'],
                             counter_id, member['estimate_x2_mdb'], member['measured_x2_mdb'],
                             member['residual_x2_mdb'], '|'.join(member['blockers'])])
    return target.getvalue().encode('utf-8')
