from array import array
from collections import defaultdict

from .registration import calibrate, encoded, position
from .windows import candidates, index_windows


def _forward(groups, eligible, size):
    """Best ordered pairing using the first groups and the first sites."""
    rows = [array('H', [0]) * (size + 1)]
    for group in range(1, len(groups) + 1):
        options = set(eligible[group - 1])
        above, row = rows[group - 1], array('H', [0]) * (size + 1)
        for site in range(1, size + 1):
            best = above[site] if above[site] > row[site - 1] else row[site - 1]
            if site - 1 in options and above[site - 1] + 1 > best:
                best = above[site - 1] + 1
            row[site] = best
        rows.append(row)
    return rows


def _backward(groups, eligible, size):
    """Best ordered pairing using the remaining groups and remaining sites."""
    total = len(groups)
    rows = [None] * (total + 1)
    rows[total] = array('H', [0]) * (size + 1)
    for group in range(total - 1, -1, -1):
        options = set(eligible[group])
        below, row = rows[group + 1], array('H', [0]) * (size + 1)
        for site in range(size - 1, -1, -1):
            best = below[site] if below[site] > row[site + 1] else row[site + 1]
            if site in options and below[site + 1] + 1 > best:
                best = below[site + 1] + 1
            row[site] = best
        rows[group] = row
    return rows


def _solve(entries, sites, index):
    """Pair one direction's events with sites by a maximum ordered pairing.

    Events are ordered by field mileage and sites by design mileage.  A pairing
    keeps that order, uses each mileage, each site and each event at most once,
    and cannot be enlarged.  Only an ownership held by every maximum pairing is
    accepted; the rest keep the basis of an unmatched, competing or
    undetermined event.
    """
    ordered = sorted(entries, key=lambda entry: entry['position'])
    groups = []
    for entry in ordered:
        if groups and groups[-1][0] == entry['position']:
            groups[-1][1].append(entry['item'])
        else:
            groups.append((entry['position'], [entry['item']]))
    place = {site['site_id']: spot for spot, site in enumerate(sites)}
    eligible = [[place[site_id] for site_id in candidates(index, at)] for at, _ in groups]
    size, total = len(sites), len(groups)
    if not total:
        return []

    prefix = _forward(groups, eligible, size)
    suffix = _backward(groups, eligible, size)
    ceiling = prefix[total][size]

    common = []
    targets = defaultdict(list)
    for _, items in groups:
        for item in items:
            if len(item['candidates']) == 1:
                targets[item['candidates'][0]].append(item)

    for group, (_, items) in enumerate(groups):
        options = eligible[group]
        if len(items) > 1:
            # One mileage may be paired once, so same-mileage events compete and
            # no maximum pairing can share out their ownership.
            for item in items:
                item['status'], item['basis'] = 'contested', 'same_mileage'
            continue
        item = items[0]
        # Best pairing when this mileage is left unused: when it still reaches
        # the ceiling the event is not needed and a peer can take its place.
        without = max(prefix[group][site] + suffix[group + 1][site] for site in range(size + 1))
        if without == ceiling:
            item['status'] = 'contested'
            item['basis'] = 'same_end' if len(options) == 1 and len(targets[item['candidates'][0]]) > 1 \
                else 'competing'
            continue
        # Every maximum pairing needs this event; compare the sites it could
        # take at the ceiling.  A lone best site is shared by all of them.
        edges = [prefix[group][site] + 1 + suffix[group + 1][site + 1] for site in options]
        best = max(edges)
        top = [site for site, value in zip(options, edges) if value == best]
        if len(top) == 1:
            common.append((item, top[0]))
        else:
            item['status'], item['basis'] = 'undetermined', 'overlap'
    return common


def match(plan, traces):
    sites = plan['sites']
    index = index_windows(sites)
    order = {site['site_id']: spot for spot, site in enumerate(sites)}
    calibrations = []
    outcomes = []
    pending = defaultdict(list)
    for trace in traces:
        calibration = calibrate(trace, plan.get('marks_mm') or [], plan['length_mm'])
        calibrations.append(calibration)
        held = calibration['status'] == 'held'
        for line, event in enumerate(trace['events'], 1):
            at = None if held else position(calibration, event['at_mm'])
            eligible = [] if at is None else sorted(candidates(index, at), key=order.get)
            item = {**event, 'line': line, 'trace_id': trace['trace_id'], 'direction': trace['direction'],
                    'along_mm': encoded(at), 'candidates': eligible, 'site_id': None, 'basis': None}
            if held:
                item['status'], item['basis'] = 'held', calibration['reason']
            elif at is None:
                item['status'], item['basis'] = 'outside', 'endpoint'
            elif not eligible:
                item['status'], item['basis'] = 'unmapped', 'no_window'
            else:
                pending[trace['direction']].append({'position': at, 'item': item})
            outcomes.append(item)
    assigned = {}
    for direction, entries in pending.items():
        for item, spot in _solve(entries, sites, index):
            item['status'], item['basis'] = 'matched', None
            item['site_id'] = sites[spot]['site_id']
            assigned[direction, sites[spot]['site_id']] = item
    return outcomes, assigned, calibrations
