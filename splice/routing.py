import re
from dataclasses import dataclass
from urllib.parse import parse_qs

from . import comparison
from .errors import Problem
from .exports import site_csv
from .limits import current, describe, register, set_measured_on, version_at, versions
from .receipts import get_trace, list_traces, receive
from .releases import get_release, issue, list_releases
from .selection import select
from .spans import create_span, list_spans
from .workbench import event_evidence, workspace

SPAN = r'/spans/(?P<span>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
TRACE = r'(?P<trace>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
EVENT = r'(?P<event>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
REVISION = r'(?P<revision>[0-9]{1,16})'
TIER = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}'


@dataclass(frozen=True)
class Download:
    data: bytes
    filename: str


def _evidence(connection, span, trace, event):
    return event_evidence(workspace(connection, span), trace, event)


def _archived_evidence(connection, span, revision, trace, event):
    snapshot = get_release(connection, span, int(revision))['snapshot']
    return event_evidence(snapshot, trace, event)


def _csv(connection, span, revision):
    return Download(site_csv(get_release(connection, span, int(revision))), f'{span}-r{revision}-sites.csv')


def _limits(connection, span, version):
    entry = version_at(connection, span, int(version))
    return {'version': entry['version'], 'digest': entry['digest'], 'tiers': entry['registry']['tiers']}


def _limit_archive(connection, span):
    return {'current': current(connection, span), 'describe': describe(connection, span),
            'versions': [{'version': item['version'], 'digest': item['digest']} for item in versions(connection, span)]}


def compare(connection, span, left, right, query):
    values = parse_qs(query, strict_parsing=False)
    if set(values) - {'archive', 'tier'}:
        raise Problem('比较参数只接受 archive 与 tier', 400)
    if 'tier' in values and 'archive' not in values:
        raise Problem('指定重判档位时必须同时给出档案版本', 400)
    archive = values.get('archive', [None])[0]
    tier = values.get('tier', [None])[0]
    if archive is not None and not re.fullmatch(r'[0-9]{1,16}', archive):
        raise Problem('档案版本必须为整数', 400)
    if tier is not None and not re.fullmatch(TIER, tier):
        raise Problem('档位编号格式无效', 400)
    return comparison.compare(connection, span, int(left), int(right), int(archive) if archive else None, tier)


def _measured(connection, span, trace, value):
    return set_measured_on(connection, span, trace, value)


READ = (
    (r'/spans', list_spans),
    (SPAN, workspace),
    (SPAN + r'/limits', _limit_archive),
    (SPAN + r'/limits/' + REVISION, _limits),
    (SPAN + r'/traces', list_traces),
    (SPAN + r'/traces/' + TRACE, get_trace),
    (SPAN + r'/evidence/' + TRACE + '/' + EVENT, _evidence),
    (SPAN + r'/releases', list_releases),
    (SPAN + r'/releases/' + REVISION, lambda db, span, revision: get_release(db, span, int(revision))),
    (SPAN + r'/releases/' + REVISION + '/sites.csv', _csv),
    (SPAN + r'/releases/' + REVISION + '/evidence/' + TRACE + '/' + EVENT, _archived_evidence),
    (SPAN + r'/compare/(?P<left>[0-9]{1,16})/(?P<right>[0-9]{1,16})', compare),
)
WRITE = (
    (r'/spans', create_span),
    (SPAN + r'/limits', register),
    (SPAN + r'/traces', receive),
    (SPAN + r'/traces/' + TRACE + r'/measured_on', _measured),
    (SPAN + r'/selection', select),
    (SPAN + r'/releases', issue),
)


def dispatch(database, path, body=None, query=''):
    for pattern, handler in WRITE if body else READ:
        match = re.fullmatch('/api/splice' + pattern, path)
        if match:
            arguments = list(match.groups())
            if body:
                arguments.append(body())
            elif handler is compare:
                arguments.append(query)
            with database.session(write=bool(body)) as connection:
                return handler(connection, *arguments)
    raise Problem('没有这个接口', 404)
