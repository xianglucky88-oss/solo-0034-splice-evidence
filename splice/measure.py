from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .errors import Problem

UNITS = ('mdb', 'db')


def _decimal(token, field):
    if isinstance(token, bool):
        raise Problem(f'{field} 必须为有限数值')
    if isinstance(token, int):
        return Decimal(token)
    if isinstance(token, float):
        return Decimal(str(token))
    if isinstance(token, str):
        try:
            value = Decimal(token.strip())
        except InvalidOperation:
            value = Decimal('nan')
    else:
        value = Decimal('nan')
    if not value.is_finite():
        raise Problem(f'{field} 必须为有限数值')
    return value


def loss_fraction(token, unit, field):
    """把分贝或毫分贝读数精确换算为毫分贝有理数，并校验半毫分贝网格。"""
    if unit not in UNITS:
        raise Problem(f'{field} 单位必须为 db 或 mdb')
    value = _decimal(token, field)
    mdb = value * 1000 if unit == 'db' else value
    scaled = mdb * 2
    if scaled != scaled.to_integral_value():
        raise Problem(f'{field} 无法精确表示到半毫分贝网格，已拒收')
    return Fraction(mdb)


def canonical_number(frac):
    """半格有理数归一为 JSON 数：整数输出 int，半毫输出 .5 浮点。"""
    if frac.denominator == 1:
        return frac.numerator
    return frac.numerator / frac.denominator


def half_away(frac):
    """就近取整，半格远离零。"""
    if frac >= 0:
        floor = frac.numerator // frac.denominator
        if (frac.numerator - floor * frac.denominator) * 2 >= frac.denominator:
            return floor + 1
        return floor
    return -half_away(-frac)


def as_fraction(value):
    """规范读数（int 或半格浮点）还原为精确有理数。"""
    if isinstance(value, Fraction):
        return value
    return Fraction(value).limit_denominator(2)
