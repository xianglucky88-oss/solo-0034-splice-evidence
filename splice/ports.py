"""实物端口标识。接续箱可以同名，端口编号与箱体共同构成实物身份。"""

from .values import fields, text


def port_from(raw, field):
    value = fields(raw, 'box', 'port')
    return {'box': text(value['box'], f'{field}箱体'), 'port': text(value['port'], f'{field}端口')}


def port_key(port):
    return (port['box'], port['port'])


def port_label(port):
    return f"{port['box']}/{port['port']}"
