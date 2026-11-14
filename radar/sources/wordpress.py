import html

from ..http import get
from ..util import log, new_project, page_lines, shorten

NAME = "opportunitiesforyouth"
API = ("https://opportunitiesforyouth.org/wp-json/wp/v2/posts"
       "?per_page=40&_fields=id,date,link,title,excerpt,content")

FUNDED = ("fully funded", "fully-funded", "all expenses", "expenses covered")
KINDS = ("fellowship", "summer school", "winter school", "exchange", "conference", "forum", "summit",
         "camp", "volunteer", "training", "delegate", "programme", "program", "academy", "bootcamp")
EXCLUDE = ("scholarship", "phd", "master", "doctoral", "postdoc", "undergraduate", "internship",
           "job", "grant", "prize", "award", "competition", "contest", "how to")

_text = {}


def _plain(rendered):
    return " ".join(page_lines(rendered or ""))


def collect(known, today, home):
    out = []
    for post in get(API, as_json=True):
        title = html.unescape(post["title"]["rendered"])
        excerpt = _plain(post["excerpt"]["rendered"])
        low = (title + " " + excerpt).lower()
        if not any(w in low for w in FUNDED) or not any(w in low for w in KINDS):
            continue
        if any(w in title.lower() for w in EXCLUDE):
            continue
        p = new_project(NAME, post["link"], title, "other")
        p["description"] = shorten(excerpt, 300) or None
        _text[p["url"]] = "\n".join(page_lines(post["content"]["rendered"]))[:9000]
        out.append(p)
    log(f"opportunitiesforyouth: {len(out)} funded programmes")
    return out


def text_for(project, home):
    return _text.get(project["url"]) or project.get("description") or ""
