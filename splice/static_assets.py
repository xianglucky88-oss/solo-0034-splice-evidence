import re
from pathlib import Path

from .errors import Problem

ROOT = Path(__file__).resolve().parent.parent
MEDIA = {'.html': 'text/html', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json'}


def asset(path):
    if path == '/':
        target = ROOT / 'web/index.html'
    elif re.fullmatch(r'/assets/[a-z][a-z-]*\.(?:mjs|css)', path):
        target = ROOT / 'web' / path.rsplit('/', 1)[-1]
    elif re.fullmatch(r'/examples/(?:plan|a|b|b-repeat|w35|w35-a|w35-b|route)\.json', path):
        target = ROOT / path[1:]
    else:
        raise Problem('没有这个页面', 404)
    if not target.is_file():
        raise Problem('页面资源不存在', 404)
    return target.read_bytes(), MEDIA[target.suffix]
