from fractions import Fraction

NEAR = 'near'
MIDDLE = 'middle'
FAR = 'far'

ROLE_LABEL = {NEAR: '近端标记', MIDDLE: '中间标记', FAR: '远端标记'}
CALIBRATION_STATUS = {
    'ok': '三处标记换算',
    'legacy': '无中间标记，沿用原换算',
    'held': '该向留置',
}
HELD_REASON = {
    'mark_count': '中间标记数量与计划不符',
    'mark_order': '仪表标记乱序',
}


def encoded(value):
    if value is None:
        return None
    return {'numerator': value.numerator, 'denominator': value.denominator}


def decoded(value):
    return Fraction(value['numerator'], value['denominator'])


def _mark(role, read_mm, at_mm):
    return {'role': role, 'read_mm': read_mm,
            'at_mm': encoded(None if at_mm is None else Fraction(at_mm))}


def calibrate(trace, plan_marks, length):
    """Build the near→far calibration of one scan.

    The plan records the field mileage of the intermediate marks; the scan
    records its instrument mileage at the near end, at every intermediate mark
    and at the far end.  Between adjacent marks equal instrument displacement
    maps to equal field displacement, so the conversion is piecewise linear and
    always reported from the A end.  A direction whose intermediate marks are
    missing, unexpected or out of instrument order is held instead of converted.
    """

    near, far = trace['near_mm'], trace['far_mm']
    given = list(trace.get('marks_mm') or [])
    expected = list(plan_marks or [])
    entry = {'trace_id': trace['trace_id'], 'direction': trace['direction'], 'status': 'ok',
             'reason': None, 'expected_mm': expected, 'marks': [], 'segments': []}

    if not expected:
        # Spans without intermediate marks keep the original two-point rule;
        # any marks a scan volunteers are reported but do not change it.
        entry['status'] = 'legacy'
        entry['supplied_mm'] = given
        start, end = (0, length) if trace['direction'] == 'a' else (length, 0)
        entry['marks'] = [_mark(NEAR, near, start), _mark(FAR, far, end)]
        entry['segments'] = [{'read_mm': near, 'at_mm': encoded(Fraction(start))},
                             {'read_mm': far, 'at_mm': encoded(Fraction(end))}]
        return entry

    # A scan walks from its near mark to its far mark, so B meets the plan
    # marks in reverse field order.
    intermediate = expected if trace['direction'] == 'a' else list(reversed(expected))
    if len(given) != len(expected):
        entry.update(status='held', reason='mark_count')
        entry['marks'] = ([_mark(NEAR, near, None)]
                          + [_mark(MIDDLE, read, None) for read in given]
                          + [_mark(FAR, far, None)])
        return entry

    start, end = (0, length) if trace['direction'] == 'a' else (length, 0)
    entry['marks'] = ([_mark(NEAR, near, start)]
                      + [_mark(MIDDLE, read, at) for read, at in zip(given, intermediate)]
                      + [_mark(FAR, far, end)])
    readings = [near] + given + [far]
    if any(right <= left for left, right in zip(readings, readings[1:])):
        entry.update(status='held', reason='mark_order')
        return entry

    pairs = [(near, start)] + list(zip(given, intermediate)) + [(far, end)]
    entry['segments'] = [{'read_mm': read, 'at_mm': encoded(Fraction(at))} for read, at in pairs]
    return entry


def position(entry, distance):
    """Convert an instrument reading to field mileage measured from the A end."""
    if entry['status'] == 'held' or not entry['segments']:
        return None
    first, last = entry['segments'][0]['read_mm'], entry['segments'][-1]['read_mm']
    if distance < first or distance > last:
        return None
    for left, right in zip(entry['segments'], entry['segments'][1:]):
        read0, read1 = left['read_mm'], right['read_mm']
        if read0 <= distance <= read1:
            at0, at1 = decoded(left['at_mm']), decoded(right['at_mm'])
            return at0 + Fraction(distance - read0, read1 - read0) * (at1 - at0)
    return None
