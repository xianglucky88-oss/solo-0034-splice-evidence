import re
from dataclasses import dataclass

from .comparison import compare
from .errors import Problem
from .exports import site_csv, version_site_csv
from .plan_versions import activate_version, list_relations, list_versions
from .receipts import get_trace, list_traces, receive
from .reconcile import reconcile
from .releases import get_release, issue, list_releases
from .selection import select
from .spans import create_span, list_spans
from .version_receipts import get_version_trace, list_version_traces, receive_version_trace
from .version_selection import select_version
from .version_workbench import (get_version_release, issue_version, list_version_releases,
                                version_workspace)
from .workbench import event_evidence, workspace

SPAN = r'/spans/(?P<span>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
TRACE = r'(?P<trace>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
EVENT = r'(?P<event>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})'
REVISION = r'(?P<revision>[0-9]{1,16})'
VERSION = r'(?P<version>[0-9]{1,16})'


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


def _version_csv(connection, span, version, revision):
    release = get_version_release(connection, span, int(version), int(revision))
    return Download(version_site_csv(release), f'{span}-v{version}-r{revision}-sites.csv')


def _version_evidence(connection, span, version, trace, event):
    return event_evidence(version_workspace(connection, span, int(version)), trace, event)


def _version_archived_evidence(connection, span, version, revision, trace, event):
    snapshot = get_version_release(connection, span, int(version), int(revision))['snapshot']
    return event_evidence(snapshot, trace, event)


def _reconcile(connection, span, left_version, left_revision, right_version, right_revision):
    return reconcile(connection, span, int(left_version), int(left_revision),
                     int(right_version), int(right_revision))
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
    (SPAN + r'/versions', list_versions),
    (SPAN + r'/versions/' + VERSION + r'/relations',
     lambda db, span, version: list_relations(db, span, int(version))),
    (SPAN + r'/versions/' + VERSION, lambda db, span, version: version_workspace(db, span, int(version))),
    (SPAN + r'/versions/' + VERSION + r'/traces',
     lambda db, span, version: list_version_traces(db, span, int(version))),
    (SPAN + r'/versions/' + VERSION + r'/traces/' + TRACE,
     lambda db, span, version, trace: get_version_trace(db, span, int(version), trace)),
    (SPAN + r'/versions/' + VERSION + r'/evidence/' + TRACE + '/' + EVENT, _version_evidence),
    (SPAN + r'/versions/' + VERSION + r'/releases',
     lambda db, span, version: list_version_releases(db, span, int(version))),
    (SPAN + r'/versions/' + VERSION + r'/releases/' + REVISION,
     lambda db, span, version, revision: get_version_release(db, span, int(version), int(revision))),
    (SPAN + r'/versions/' + VERSION + r'/releases/' + REVISION + r'/sites.csv', _version_csv),
    (SPAN + r'/versions/' + VERSION + r'/releases/' + REVISION + r'/evidence/' + TRACE + '/' + EVENT,
     _version_archived_evidence),
    (SPAN + r'/reconcile/(?P<left_version>[0-9]{1,16})/(?P<left_revision>[0-9]{1,16})/'
     r'(?P<right_version>[0-9]{1,16})/(?P<right_revision>[0-9]{1,16})', _reconcile),
)
WRITE = (
    (r'/spans', create_span),
    (SPAN + r'/traces', receive),
    (SPAN + r'/selection', select),
    (SPAN + r'/releases', issue),
    (SPAN + r'/versions', activate_version),
    (SPAN + r'/versions/' + VERSION + r'/traces',
     lambda db, span, version, body: receive_version_trace(db, span, int(version), body)),
    (SPAN + r'/versions/' + VERSION + r'/selection',
     lambda db, span, version, body: select_version(db, span, int(version), body)),
    (SPAN + r'/versions/' + VERSION + r'/releases',
     lambda db, span, version, body: issue_version(db, span, int(version), body)),
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
