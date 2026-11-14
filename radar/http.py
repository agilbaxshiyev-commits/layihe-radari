import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

UA = "LayiheRadar/0.1 (personal opportunity tracker; respects robots.txt)"
DELAY_SECONDS = 1.5

_session = requests.Session()
_session.headers["User-Agent"] = UA
_last_hit = {}
_robots = {}
_cache = {}


class Blocked(Exception):
    pass


def _origin(url):
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def _allowed(url):
    origin = _origin(url)
    parser = _robots.get(origin)
    if parser is None:
        parser = urllib.robotparser.RobotFileParser()
        try:
            resp = _session.get(origin + "/robots.txt", timeout=20)
            parser.parse(resp.text.splitlines() if resp.ok else [])
        except requests.RequestException:
            parser.parse([])
        _robots[origin] = parser
    return parser.can_fetch(UA, url)


def get(url, as_json=False):
    """Polite GET: one request per host every DELAY_SECONDS, robots.txt honoured, cached per run."""
    if url in _cache:
        return _cache[url]
    if not _allowed(url):
        raise Blocked(f"robots.txt disallows {url}")
    origin = _origin(url)
    wait = DELAY_SECONDS - (time.monotonic() - _last_hit.get(origin, 0))
    if wait > 0:
        time.sleep(wait)
    resp = _session.get(url, timeout=30)
    _last_hit[origin] = time.monotonic()
    resp.raise_for_status()
    result = resp.json() if as_json else resp.content.decode("utf-8", errors="replace")
    _cache[url] = result
    return result
