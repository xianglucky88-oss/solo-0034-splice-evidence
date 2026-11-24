import argparse
from pathlib import Path

from .db import Database
from .server import serve


def main():
    parser = argparse.ArgumentParser(description='启动纤证接续损耗交接台')
    parser.add_argument('--port', default=8734, type=int)
    parser.add_argument('--db', default=Path('splice-evidence.sqlite3'), type=Path)
    args = parser.parse_args()
    with serve(Database(args.db), args.port) as server:
        print(f'工作台 http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
