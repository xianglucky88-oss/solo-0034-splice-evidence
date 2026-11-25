import csv
from io import StringIO


def site_csv(release):
    target = StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'tier_id', 'registry_version', 'site_id', 'design_mm',
                     'mean_x2_mdb', 'limit_mdb', 'a_trace', 'a_event', 'b_trace', 'b_event'])
    snapshot = release['snapshot']
    tier = snapshot.get('tier') or {}
    tier_id = tier.get('tier_id') or ''
    version = tier.get('registry_version') if tier.get('registry_version') is not None else ''
    for site in snapshot['sites']:
        a, b = (site['observations'][side] for side in ('a', 'b'))
        writer.writerow([snapshot['plan']['span_id'], snapshot['revision'], release['digest'], tier_id, version,
                         site['site_id'], site['at_mm'], site['mean_x2_mdb'], site['limit_mdb'],
                         a['trace_id'], a['event_id'], b['trace_id'], b['event_id']])
    return target.getvalue().encode('utf-8')
