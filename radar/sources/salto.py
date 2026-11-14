import re

from bs4 import BeautifulSoup

from ..http import get
from ..util import (home_status, iso, log, new_project, page_lines, parse_costs, parse_date,
                    parse_range, set_dates, shorten, split_countries)

NAME = "salto"
LIST_URL = "https://www.salto-youth.net/tools/european-training-calendar/browse/"
PREFIX = "https://www.salto-youth.net/tools/european-training-calendar/training/"

_text = {}


def _txt(node):
    return node.get_text(" ", strip=True) if node else ""


def _card(item, home):
    link = item.select_one("h2.tool-item-name a")
    if not link or not link.get("href", "").startswith(PREFIX):
        return None
    category = _txt(item.select_one(".tool-item-category"))
    location = _txt(item.select_one("p.microcopy.mrgn-btm-17"))
    if "e-learning" in category.lower() or location.lower().startswith("online"):
        return None
    p = new_project(NAME, link["href"], link.get_text(strip=True), "training_course")
    p["type_label"] = category or None
    set_dates(p, *parse_range(_txt(item.select_one("p.h5"))))
    city, _, country = location.rpartition(", ")
    p["city"], p["host_country"] = city or None, country or None
    p["description"] = shorten(_txt(item.select_one("p.mrgn-btm-22.h5")), 300) or None
    p["deadline"] = iso(parse_date(_txt(item.select_one(".callout-module p.h3"))))

    who = _txt(item.select_one(".tool-item-short-overview p.tightened-bodycopy"))
    # SALTO names either countries or groups such as "Erasmus+ Youth Programme countries".
    if "countr" in who.lower():
        p["eligible_note"] = who.replace(" ,", ",")
    else:
        p["eligible_countries"] = [c.title() if c.isupper() else c for c in split_countries(who)]
    p["az_eligible"] = home_status([], home, complete=True, extra_text=who)
    return p


def _detail(html_text, title):
    lines = page_lines(html_text)
    end = lines.index("Disclaimer!") if "Disclaimer!" in lines else len(lines)
    starts = [i for i, line in enumerate(lines[:end]) if line == title]
    body = lines[starts[-1] + 1:end] if starts else []

    overview = []
    if "Training overview" in lines:
        i = lines.index("Training overview")
        for line in lines[i:i + 60]:
            if line.startswith("Contact for questions"):
                break
            overview.append(line)
    costs = []
    if "Costs" in lines:
        i = len(lines) - 1 - lines[::-1].index("Costs")
        costs = lines[i:i + 25]

    out = {"detail": True, "costs": parse_costs(" ".join(costs))}
    joined = " ".join(overview)
    total = re.search(r"(\d+)\s+participants", joined)
    out["spots_total"] = int(total.group(1)) if total else None
    organiser = re.search(r"Organiser:\s*(.+?)\s*(?:\(|Co-organiser|$)", joined)
    out["organizer"] = organiser.group(1).strip() if organiser else None
    text = "\n".join(body + ["--- Overview ---"] + overview + ["--- Costs ---"] + costs)
    return out, text[:9000]


def collect(known, today, home):
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    out, fetched = [], 0
    for item in soup.select("div.tool-item"):
        p = _card(item, home)
        if not p:
            continue
        prev = known.get(p["url"])
        expired = p["deadline"] and p["deadline"] < today.isoformat()
        if not expired and p["az_eligible"] != "no" and not (prev and prev.get("detail")):
            try:
                extra, text = _detail(get(p["url"]), p["title"])
                p.update(extra)
                _text[p["url"]] = text
                fetched += 1
            except Exception as exc:
                log(f"salto detail failed for {p['url']}: {exc}")
        if not expired or prev:
            out.append(p)
    log(f"salto: {len(out)} trainings, {fetched} detail pages read")
    return out


def text_for(project, home):
    if project["url"] not in _text:
        _, _text[project["url"]] = _detail(get(project["url"]), project["title"])
    return _text[project["url"]]
