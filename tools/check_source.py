"""Check the source without generating caches or installing dependencies."""

from pathlib import Path
import sqlite3
import subprocess
from contextlib import closing


def main():
    root = Path(__file__).resolve().parents[1]
    for package in ('splice', 'tools'):
        for path in sorted((root / package).glob('*.py')):
            compile(path.read_bytes(), str(path), 'exec')
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.executescript((root / 'splice' / 'schema.sql').read_text(encoding='utf-8'))
    for path in sorted((root / 'web').glob('*.mjs')):
        subprocess.run(['node', '--check', str(path)], check=True)
    print('Python、SQLite DDL 和浏览器模块检查通过')


if __name__ == '__main__':
    main()
