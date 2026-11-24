from collections import defaultdict

from .registration import coordinate, encoded
from .windows import candidates, index_windows


def match(plan, traces):
    windows = index_windows(plan['sites'])
    outcomes = []
    singles = defaultdict(list)
    for trace in traces:
        for line, event in enumerate(trace['events'], 1):
            position = coordinate(trace, event['at_mm'], plan['length_mm'])
            eligible = [] if position is None else candidates(windows, position)
            item = {**event, 'line': line, 'trace_id': trace['trace_id'], 'direction': trace['direction'],
                    'along_mm': encoded(position), 'candidates': eligible}
            if position is None:
                item['status'] = 'outside'
            elif not eligible:
                item['status'] = 'unmapped'
            elif len(eligible) > 1:
                item['status'] = 'ambiguous'
            else:
                item['status'] = 'matched'
                singles[trace['direction'], eligible[0]].append(item)
            outcomes.append(item)
    assigned = {}
    for slot, items in singles.items():
        if len(items) == 1:
            assigned[slot] = items[0]
        else:
            for item in items:
                item['status'] = 'collision'
    return outcomes, assigned
