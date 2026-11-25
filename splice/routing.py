import re
from dataclasses import dataclass

from .comparison import compare
from .errors import Problem
from .exports import site_csv
from .receipts import get_trace, list_traces, receive
from .releases import get_release, issue, list_releases
from .route_exports import route_csv
from .routes import (create_route, get_route_release, issue_route, list_route_releases, list_routes,
                     route_workspace)
from .selection import select
from .spans import create_span, list_spans
from .workbench import event_evidence, workspace

SPAN = r'/spans/(?P<span>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
TRACE = r'(?P<trace>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
EVENT = r'(?P<event>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
REVISION = r'(?P<revision>[0-9]{1,16})'
ROUTE = r'/routes/(?P<route>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
SHA = r'(?P<sha>[0-9a-f]{64})'


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


def _route_csv(connection, route, sha):
    return Download(route_csv(get_route_release(connection, route, sha)), f'{route}-{sha[:12]}.csv')


READ = (
    (r'/spans', list_spans),
    (SPAN, workspace),
    (SPAN + r'/traces', list_traces),
    (SPAN + r'/traces/' + TRACE, get_trace),
    (SPAN + r'/evidence/' + TRACE + '/' + EVENT, _evidence),
    (SPAN + r'/releases', list_releases),
    (SPAN + r'/releases/' + REVISION, lambda db, span, revision: get_release(db, span, int(revision))),
    (SPAN + r'/releases/' + REVISION + '/sites.csv', _csv),
    (SPAN + r'/releases/' + REVISION + '/evidence/' + TRACE + '/' + EVENT, _archived_evidence),
    (SPAN + r'/compare/(?P<left>[0-9]{1,16})/(?P<right>[0-9]{1,16})',
     lambda db, span, left, right: compare(db, span, int(left), int(right))),
    (r'/routes', list_routes),
    (ROUTE, route_workspace),
    (ROUTE + r'/releases', list_route_releases),
    (ROUTE + r'/releases/' + SHA, get_route_release),
    (ROUTE + r'/releases/' + SHA + r'/parts.csv', _route_csv),
)
WRITE = (
    (r'/spans', create_span),
    (SPAN + r'/traces', receive),
    (SPAN + r'/selection', select),
    (SPAN + r'/releases', issue),
    (r'/routes', create_route),
    (ROUTE + r'/releases', issue_route),
)


def dispatch(database, path, body=None):
    for pattern, handler in WRITE if body else READ:
        match = re.fullmatch('/api/splice' + pattern, path)
        if match:
            arguments = match.groups()
            if body:
                arguments += (body(),)
            with database.session(write=bool(body)) as connection:
                return handler(connection, *arguments)
    raise Problem('没有这个接口', 404)
