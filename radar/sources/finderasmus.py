import re

from bs4 import BeautifulSoup

from ..http import get
from ..util import (between, home_status, iso, log, new_project, page_lines, parse_costs,
                    parse_date, parse_range, set_dates, shorten, split_countries)

NAME = "finderasmus"
LIST_URL = "https://finderasmus.eu/projects.html"
PREFIX = "https://finderasmus.eu/projects/"
MAX_DETAILS_PER_RUN = 120
LABELS = ["Type", "Dates", "Location", "Who can apply", "Participants", "Working language", "Costs",
          "Organisers", "Deadline", "How to apply"]

_text = {}


def _kind(badge):
    low = badge.lower()
    if "exchange" in low:
        return "youth_exchange"
    if "volunteer" in low or "solidarity" in low:
        return "esc_volunteering"
    if "training" in low or "seminar" in low:
        return "training_course"
    return "other"


def _card(card, home):
    link = card.select_one("h3 a")
    if not link or not link.get("href", "").startswith(PREFIX):
        return None
    badge = card.select_one(".type-badge")
    badge = badge.get_text(strip=True) if badge else ""
    p = new_project(NAME, link["href"], link.get_text(strip=True), _kind(badge))
    p["type_label"] = badge or None

    dates = card.select_one("p.dates")
    set_dates(p, *parse_range(dates.get_text(" ", strip=True) if dates else ""))
    location = card.select_one("p.location")
    if location:
        city, _, country = location.get_text(" ", strip=True).rpartition(", ")
        p["city"], p["host_country"] = city or None, country or None
    excerpt = card.select_one(".project-card-excerpt")
    p["description"] = shorten(excerpt.get_text(" ", strip=True), 300) if excerpt else None

    countries, complete = [], True
    for line in card.select("p.spots"):
        text = line.get_text(" ", strip=True)
        if text.startswith("Apply by"):
            p["deadline"] = iso(parse_date(text))
        elif text.startswith("Open to:"):
            complete = "and more" not in text.lower()
            countries = split_countries(text[len("Open to:"):])
        elif text.startswith("Topics:"):
            p["topics"] = [t.strip() for t in text[len("Topics:"):].split(",") if t.strip()]
    p["eligible_countries"] = countries
    p["az_eligible"] = home_status(countries, home, complete)
    return p


def _detail(html_text, home):
    lines = page_lines(html_text)
    stop_key = lambda l: l in ("What you will do", "Questions & answers", "Topics", "Eligible Countries")
    fields, current = {}, None
    for line in between(lines, "Key details", stop_key):
        if line in LABELS:
            current = line
            fields[current] = []
        elif current:
            fields[current].append(line)
    field = lambda name: " ".join(fields.get(name, []))

    out = {"detail": True}
    countries = split_countries(", ".join(between(lines, "Eligible Countries", lambda l: l == "Description")))
    if countries:
        out["eligible_countries"] = countries
        out["az_eligible"] = home_status(countries, home, complete=True)

    who = field("Who can apply")
    age = re.search(r"[Aa]ged\s+(\d{1,2})\s*(?:(?:[–-]|to)\s*(\d{1,2})|\+)?", who)
    if age:
        out["age_min"] = int(age.group(1))
        out["age_max"] = int(age.group(2)) if age.group(2) else None

    spots = field("Participants")
    per = re.search(r"(\d+)\s+per country", spots)
    total = re.search(r"(\d+)\s+in total", spots)
    out["spots_per_country"] = int(per.group(1)) if per else None
    out["spots_total"] = int(total.group(1)) if total else None

    description = " ".join(between(
        lines, "Description",
        lambda l: l.startswith(("Apply", "Download Infopack")) or l == "Project Details"))
    out["costs"] = parse_costs(field("Costs") + ". " + description)
    host = re.search(r"Host:\s*([^;]+)", field("Organisers"))
    out["organizer"] = host.group(1).strip() if host else None
    if description:
        out["description"] = shorten(description, 300)

    main = between(lines, "Key details", lambda l: l == "Project Details")
    return out, "\n".join(main)[:8000]


def collect(known, today, home):
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    out, fetched = [], 0
    for card in soup.select("article.project-card"):
        p = _card(card, home)
        if not p:
            continue
        prev = known.get(p["url"])
        expired = p["deadline"] and p["deadline"] < today.isoformat()
        wants_detail = not expired and p["az_eligible"] != "no" and not (prev and prev.get("detail"))
        if wants_detail and fetched < MAX_DETAILS_PER_RUN:
            try:
                extra, text = _detail(get(p["url"]), home)
                p.update(extra)
                _text[p["url"]] = text
                fetched += 1
            except Exception as exc:
                log(f"finderasmus detail failed for {p['url']}: {exc}")
        if not expired or prev:
            out.append(p)
    log(f"finderasmus: {len(out)} projects, {fetched} detail pages read")
    return out


def text_for(project, home):
    if project["url"] not in _text:
        _, _text[project["url"]] = _detail(get(project["url"]), home)
    return _text[project["url"]]
