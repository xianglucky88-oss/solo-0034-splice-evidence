import datetime
import hashlib

from .codec import unpack
from .errors import Problem
from .trace import DIRECTIONS
from .values import fields, key, text

STATED = 'stated'
UNSTATED = 'unstated'


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _notice(row):
    return {'notice_id': row['notice_id'], 'instrument_id': row['instrument_id'],
            'calibration_batch': row['calibration_batch'], 'note': row['note'], 'revoked_at': row['revoked_at']}


def derived_notice_id(instrument_id, calibration_batch):
    digest = hashlib.sha256(f'{instrument_id}\x1f{calibration_batch}'.encode()).hexdigest()
    return 'RV-' + digest[:12]


def identity(instrument_id, calibration_batch):
    if instrument_id is None or calibration_batch is None:
        return {'instrument_id': None, 'calibration_batch': None, 'source': UNSTATED}
    return {'instrument_id': instrument_id, 'calibration_batch': calibration_batch, 'source': STATED}


def trace_identity(trace):
    return identity(trace.get('instrument_id'), trace.get('calibration_batch'))


def notices(connection):
    return [_notice(row) for row in connection.execute(
        'SELECT * FROM revocations ORDER BY revoked_at, notice_id')]


def notice_pairs(connection):
    return {(item['instrument_id'], item['calibration_batch']): item for item in notices(connection)}


def revoke(connection, raw):
    fields(raw, 'instrument_id', 'calibration_batch', optional=('notice_id', 'note'))
    instrument = key(raw['instrument_id'], '仪表编号')
    batch = key(raw['calibration_batch'], '校验批次')
    note = text(raw['note'], '撤销说明') if raw.get('note') is not None else None
    requested = key(raw['notice_id'], '撤销通知编号') if raw.get('notice_id') is not None else None
    existing = connection.execute(
        'SELECT * FROM revocations WHERE instrument_id = ? AND calibration_batch = ?',
        (instrument, batch)).fetchone()
    if existing is not None:
        if requested is not None and requested != existing['notice_id']:
            raise Problem('该仪表与校验批次已由另一撤销通知生效', 409)
        current = _notice(existing)
        return {**current, 'replayed': True, 'impacts': impacts(connection, current)}
    notice_id = requested or derived_notice_id(instrument, batch)
    if connection.execute('SELECT 1 FROM revocations WHERE notice_id = ?', (notice_id,)).fetchone():
        raise Problem('撤销通知编号已经绑定其他校验批次', 409)
    connection.execute('INSERT INTO revocations VALUES (?, ?, ?, ?, ?)',
                       (notice_id, instrument, batch, note, _stamp()))
    current = _notice(connection.execute('SELECT * FROM revocations WHERE notice_id = ?', (notice_id,)).fetchone())
    return {**current, 'replayed': False, 'impacts': impacts(connection, current)}


def get_notice(connection, notice_id):
    row = connection.execute('SELECT * FROM revocations WHERE notice_id = ?', (notice_id,)).fetchone()
    if row is None:
        raise Problem('未找到该撤销通知', 404)
    current = _notice(row)
    return {**current, 'impacts': impacts(connection, current)}


def list_notices(connection):
    return [{**current, 'impacts': impacts(connection, current)} for current in notices(connection)]


def _adopted_identity(connection, span_id, meta):
    """以签发或采用当时记录的仪表与批次为准；旧资料标注来源未注明。"""
    if not meta:
        return {'trace_id': None, **identity(None, None)}
    return {'trace_id': meta.get('trace_id'), **identity(meta.get('instrument_id'), meta.get('calibration_batch'))}


def impacts(connection, current):
    """按实际引用归类：未采用凭证、在用工作修订、已签修订。"""
    target = (current['instrument_id'], current['calibration_batch'])
    receipts, working, releases = [], [], []
    for span in connection.execute('SELECT span_id, revision FROM spans ORDER BY span_id'):
        span_id = span['span_id']
        active = {row['direction']: row['trace_id'] for row in connection.execute(
            'SELECT direction, trace_id FROM active_traces WHERE span_id = ?', (span_id,))}
        for row in connection.execute(
                'SELECT trace_id, direction FROM traces WHERE span_id = ? '
                'AND instrument_id = ? AND calibration_batch = ? ORDER BY direction, trace_id', (span_id, *target)):
            adopted = active.get(row['direction']) == row['trace_id']
            receipts.append({'span_id': span_id, 'trace_id': row['trace_id'], 'direction': row['direction'],
                             'adopted': adopted, 'notice_id': current['notice_id']})
            if adopted:
                working.append({'span_id': span_id, 'revision': span['revision'], 'side': row['direction'],
                                'trace_id': row['trace_id'], 'notice_id': current['notice_id']})
        for release in connection.execute(
                'SELECT revision, digest, payload FROM releases WHERE span_id = ? ORDER BY revision', (span_id,)):
            affected = _release_marks(connection, span_id, unpack(release['payload']), target)
            if affected:
                releases.append({'span_id': span_id, 'revision': release['revision'], 'digest': release['digest'],
                                 'affected': affected, 'notice_id': current['notice_id']})
    return {'receipts': receipts, 'working': working, 'releases': releases}


def _release_marks(connection, span_id, snapshot, target):
    marks = []
    for side in DIRECTIONS:
        meta = (snapshot.get('active') or {}).get(side)
        if not meta:
            continue
        adopted = _adopted_identity(connection, span_id, meta)
        if adopted['source'] == STATED and (adopted['instrument_id'], adopted['calibration_batch']) == target:
            marks.append({'side': side, **adopted})
    return marks


def assess_release(connection, span_id, snapshot, pairs=None):
    """现时交接状态：所采用的凭证是否属于已撤销批次。"""
    pairs = notice_pairs(connection) if pairs is None else pairs
    adopted_items, affected = [], []
    for side in DIRECTIONS:
        meta = (snapshot.get('active') or {}).get(side)
        if not meta:
            continue
        adopted = _adopted_identity(connection, span_id, meta)
        notice = pairs.get((adopted['instrument_id'], adopted['calibration_batch'])) \
            if adopted['source'] == STATED else None
        item = {'side': side, **adopted, 'notice': notice}
        adopted_items.append(item)
        if notice is not None:
            affected.append(item)
    return {'status': 'blocked' if affected else 'clear', 'adopted': adopted_items, 'affected': affected}


def receipt_impacts(connection, span_id, pairs=None):
    """收件层面的撤销标注，未采用凭证只作为收件影响。"""
    pairs = notice_pairs(connection) if pairs is None else pairs
    active = {row['direction']: row['trace_id'] for row in connection.execute(
        'SELECT direction, trace_id FROM active_traces WHERE span_id = ?', (span_id,))}
    items = []
    for row in connection.execute(
            'SELECT trace_id, direction, digest, instrument_id, calibration_batch FROM traces '
            'WHERE span_id = ? ORDER BY direction, trace_id', (span_id,)):
        source = identity(row['instrument_id'], row['calibration_batch'])
        notice = pairs.get((row['instrument_id'], row['calibration_batch'])) \
            if source['source'] == STATED else None
        items.append({'trace_id': row['trace_id'], 'direction': row['direction'], 'digest': row['digest'],
                      **source, 'adopted': active.get(row['direction']) == row['trace_id'], 'notice': notice})
    return items
