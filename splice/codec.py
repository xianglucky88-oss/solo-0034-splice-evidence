import hashlib
import json

from .errors import Problem


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Problem(f'JSON 字段重复：{key}', 400)
        result[key] = value
    return result


def _invalid_constant(_):
    raise Problem('JSON 数字必须为有限值', 400)


def unpack(data):
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise Problem('请求必须为 UTF-8 JSON', 400) from exc


def digest(data):
    return hashlib.sha256(data).hexdigest()
