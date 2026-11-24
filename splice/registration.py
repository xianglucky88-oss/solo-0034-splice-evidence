from fractions import Fraction


def coordinate(trace, distance, length):
    near, far = trace['near_mm'], trace['far_mm']
    if distance < near or distance > far:
        return None
    forward = Fraction((distance - near) * length, far - near)
    return forward if trace['direction'] == 'a' else length - forward


def encoded(coordinate_value):
    if coordinate_value is None:
        return None
    return {'numerator': coordinate_value.numerator, 'denominator': coordinate_value.denominator}
