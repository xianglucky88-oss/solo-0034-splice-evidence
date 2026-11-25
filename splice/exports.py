import csv
from io import StringIO

from .measure import as_fraction, canonical_number


def site_csv(release):
    target = StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'site_id', 'design_mm', 'mean_x2_mdb',
                     'booked_mean_x2_mdb', 'limit_mdb', 'a_trace', 'a_event', 'b_trace', 'b_event'])
    snapshot = release['snapshot']
    booked = {item['site_id']: item for item in snapshot['delivery']['sites']}
    for site in snapshot['sites']:
        a, b = (site['observations'][side] for side in ('a', 'b'))
        booked_site = booked.get(site['site_id'])
        writer.writerow([
            snapshot['plan']['span_id'], snapshot['revision'], release['digest'], site['site_id'],
            site['at_mm'], site['mean_x2_mdb'],
            booked_site['mean_x2_mdb'] if booked_site else '', site['limit_mdb'],
            a['trace_id'], a['event_id'], b['trace_id'], b['event_id']])
    return target.getvalue().encode('utf-8')


def delivery_csv(release):
    target = StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(['span_id', 'revision', 'snapshot_sha256', 'scope', 'direction', 'site_id', 'design_mm',
                     'trace_id', 'event_id', 'original_mdb', 'booked_mdb', 'limit_mdb'])
    snapshot = release['snapshot']
    delivery = snapshot['delivery']
    labels = {'a': '甲端', 'b': '乙端'}
    for side in ('a', 'b'):
        for site in delivery['sites']:
            observation = site['observations'][side]
            writer.writerow([
                snapshot['plan']['span_id'], snapshot['revision'], release['digest'], 'site', labels[side],
                site['site_id'], site['at_mm'], observation['trace_id'], observation['event_id'],
                observation['original_mdb'], observation['booked_mdb'], site['limit_mdb']])
        writer.writerow([
            snapshot['plan']['span_id'], snapshot['revision'], release['digest'], 'site_total', labels[side],
            '', '', '', '',
            canonical_number(sum((as_fraction(item['observations'][side]['original_mdb'])
                                  for item in delivery['sites']), start=as_fraction(0))),
            delivery['site_totals_mdb'][side], ''])
        writer.writerow([
            snapshot['plan']['span_id'], snapshot['revision'], release['digest'], 'span_total', labels[side],
            '', '', '', '', snapshot['budget']['totals_mdb'][side], delivery['totals_mdb'][side], ''])
    for scope, booked_value in (
        ('estimate_x2_mdb', delivery['estimate_x2_mdb']),
        ('measured_x2_mdb', delivery['measured_x2_mdb']),
        ('residual_x2_mdb', delivery['residual_x2_mdb']),
    ):
        writer.writerow([snapshot['plan']['span_id'], snapshot['revision'], release['digest'], scope,
                         '', '', '', '', '', '', booked_value, ''])
    return target.getvalue().encode('utf-8')
