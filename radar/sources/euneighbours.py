from bs4 import BeautifulSoup

from ..http import get
from ..util import iso, log, new_project, page_lines, parse_date, shorten

NAME = "euneighbours"
LIST_URL = "https://euneighbourseast.eu/opportunities/"
PREFIX = "https://euneighbourseast.eu/opportunities/"
OTHER_COUNTRIES = ("armenia", "belarus", "georgia", "moldova", "ukraine")
SKIP_WORDS = ("webinar", "online course", "e-learning", "tutorial", "info session", "mooc")
STOP_LINES = ("Share", "MOST READ", "See also", "Related", "Latest news", "Interested in the latest news")

_text = {}


def _article(html_text, title):
    lines = page_lines(html_text)
    starts = [i for i, line in enumerate(lines) if line == title]
    if not starts:
        return ""
    body = []
    for line in lines[starts[-1] + 1:starts[-1] + 160]:
        if line.startswith(STOP_LINES):
            break
        body.append(line)
    return "\n".join(body)[:8000]


def collect(known, today, home):
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    out = []
    for link in soup.select("a.el-item"):
        url = link.get("href", "")
        title_node = link.select_one(".el-title")
        if not url.startswith(PREFIX) or not title_node:
            continue
        title = title_node.get_text(" ", strip=True)
        low = title.lower()
        if any(word in low for word in SKIP_WORDS):
            continue
        if any(c in low for c in OTHER_COUNTRIES) and home.lower() not in low:
            continue
        p = new_project(NAME, url, title, "other")
        meta = link.select_one(".el-meta")
        p["deadline"] = iso(parse_date(meta.get_text(" ", strip=True) if meta else ""))
        excerpt = link.select_one(".el-content")
        excerpt = excerpt.get_text(" ", strip=True) if excerpt else ""
        p["description"] = shorten(excerpt, 300) or None
        if home.lower() in (title + " " + excerpt).lower():
            p["az_eligible"] = "yes"
        if p["deadline"] and p["deadline"] < today.isoformat() and url not in known:
            continue
        out.append(p)
    log(f"euneighbours: {len(out)} opportunities")
    return out


def text_for(project, home):
    if project["url"] not in _text:
        _text[project["url"]] = _article(get(project["url"]), project["title"])
    return _text[project["url"]] or project.get("description") or ""
