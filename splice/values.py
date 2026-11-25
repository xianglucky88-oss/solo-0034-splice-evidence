import re

from .errors import Problem

KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}', re.ASCII)


def key(value, field):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise Problem(f'{field} 必须为 1 至 48 位字母、数字、点、下划线或连字符，且以字母或数字开头')
    return value


def text(value, field):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
        raise Problem(f'{field} 必须为 1 至 80 个字符')
    return value.strip()


def integer(value, field, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Problem(f'{field} 必须为 {low} 至 {high} 的整数')
    return value


def fields(value, *required, optional=()):
    if not isinstance(value, dict):
        raise Problem(f'应提供以下字段：{", ".join(required)}')
    missing = [name for name in required if name not in value]
    extra = [name for name in value if name not in required and name not in optional]
    if missing or extra:
        raise Problem(f'字段与资料要求不符，应提供：{", ".join(required)}')
    return value


def rows(value, field, low, high):
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise Problem(f'{field} 必须含 {low} 至 {high} 行')
    return value
