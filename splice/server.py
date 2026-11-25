from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .codec import pack, unpack
from .errors import Problem
from .routing import Download, dispatch
from .static_assets import asset

MAX_BODY = 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request(self.body)

    def body(self):
        if self.headers.get_content_type() != 'application/json':
            raise Problem('请通过 application/json 发送测量资料', 415)
        lengths = self.headers.get_all('Content-Length') or []
        length = lengths[0] if len(lengths) == 1 else ''
        if self.headers.get('Transfer-Encoding') or not length.isascii() or not length.isdigit() or len(length) > 8:
            raise Problem('请求需要有效的 Content-Length', 400)
        size = int(length)
        if size > MAX_BODY:
            raise Problem('单次请求不能超过 1 MiB', 413)
        payload = self.rfile.read(size)
        if len(payload) != size:
            raise Problem('请求正文提前结束', 400)
        return unpack(payload)

    def answer(self, status, data, kind='application/json', filename=None):
        self.send_response(status)
        self.send_header('Content-Type', f'{kind}; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self, read_body=None):
        try:
            hosts = self.headers.get_all('Host') or []
            port = self.server.server_port
            if len(hosts) != 1 or hosts[0] not in (f'localhost:{port}', f'127.0.0.1:{port}'):
                raise Problem('仅接受本机工作台地址', 400)
            if read_body and self.headers.get('Origin') not in (None, 'http://' + hosts[0]):
                raise Problem('请求来源与工作台地址不一致', 403)
            path = urlsplit(self.path).path
            if path.startswith('/api/splice/') or read_body:
                query = urlsplit(self.path).query
                result = dispatch(self.server.database, path, read_body, query)
                if isinstance(result, Download):
                    self.answer(200, result.data, 'text/csv', result.filename)
                else:
                    self.answer(200, pack(result))
            else:
                data, kind = asset(path)
                self.answer(200, data, kind)
        except Problem as error:
            self.answer(error.status, pack({'error': str(error)}))
        except ValueError:
            self.answer(400, pack({'error': '请求地址或内容格式无效'}))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return


def serve(database, port):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.database = database
    return server
