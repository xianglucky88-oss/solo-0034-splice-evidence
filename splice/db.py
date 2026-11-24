import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import Problem


class Database:
    def __init__(self, path):
        self.path = path
        with self.connect() as connection:
            connection.execute('PRAGMA journal_mode = WAL')
            connection.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=4, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys = ON')
            yield connection
        finally:
            connection.close()

    @contextmanager
    def session(self, *, write=False):
        try:
            with self.connect() as connection:
                connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                try:
                    yield connection
                    connection.execute('COMMIT')
                except BaseException:
                    if connection.in_transaction:
                        connection.execute('ROLLBACK')
                    raise
        except sqlite3.OperationalError as exc:
            if getattr(exc, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise Problem('存储繁忙，请稍后重试', 503) from exc
            raise
