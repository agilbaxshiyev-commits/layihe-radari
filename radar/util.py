import hashlib
import re
from datetime import date

from bs4 import BeautifulSoup

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

_DMY = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})")
_MDY = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")
_RANGE_SPLIT = re.compile(r"\s*[–—]\s*|\s+-\s+|(?<=\d)-(?=\d)")

COUNTRY_ALIASES = {
    "turkey": "Türkiye", "turkiye": "Türkiye", "türkiye": "Türkiye",
    "czech republic": "Czechia", "the netherlands": "Netherlands",
    "republic of north macedonia": "North Macedonia", "uk": "United Kingdom",
}


def pid(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def log(msg):
    print(f"[radar] {msg}", flush=True)


def _month(name):
    return MONTHS.get((name or "").lower()[:3])


def _make(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def parse_date(text):
    if not text:
        return None
    m = _DMY.search(text)
    if m and _month(m.group(2)):
        return _make(m.group(3), _month(m.group(2)), m.group(1))
    m = _MDY.search(text)
    if m and _month(m.group(1)):
        return _make(m.group(3), _month(m.group(1)), m.group(2))
    return None


def parse_range(text):
    """Parse '24 Feb – 4 Mar 2027', '11-19 January 2027' or 'July 20 – 29, 2027'."""
    if not text:
        return None, None
    parts = _RANGE_SPLIT.split(text.strip(), maxsplit=1)
    if len(parts) == 1:
        single = parse_date(text)
        return single, single
    left, right = parts
    end = parse_date(right)
    start = parse_date(left)
    if end is None:
        tail = re.match(r"\s*(\d{1,2}),?\s+(\d{4})", right)
        head = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})", left)
        if tail and head and _month(head.group(1)):
            month = _month(head.group(1))
            return _make(tail.group(2), month, head.group(2)), _make(tail.group(2), month, tail.group(1))
        return start, None
    if start is None:
        m = re.search(r"(\d{1,2})(?:\s+([A-Za-z]{3,9}))?", left)
        if m:
            month = _month(m.group(2)) or end.month
            start = _make(end.year, month, m.group(1))
            if start and start > end:
                start = _make(end.year - 1, month, m.group(1))
    return start, end


def iso(d):
    return d.isoformat() if d else None


def from_iso(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


AZ_MONTHS = ["Yan", "Fev", "Mar", "Apr", "May", "İyn", "İyl", "Avq", "Sen", "Okt", "Noy", "Dek"]


def az_date(value):
    d = from_iso(value)
    return f"{d.day} {AZ_MONTHS[d.month - 1]} {d.year}" if d else "məlum deyil"


def norm_country(name):
    name = re.sub(r"\s+", " ", (name or "").strip(" .;"))
    return COUNTRY_ALIASES.get(name.lower(), name)


def split_countries(text):
    text = re.sub(r"\band more\b.*$", "", text or "", flags=re.I)
    return [c for c in (norm_country(part) for part in re.split(r"[,;]", text)) if c]


def new_project(source, url, title, kind):
    return {
        "id": pid(url), "source": source, "url": url, "title": title, "type": kind, "type_label": None,
        "host_country": None, "city": None, "start_date": None, "end_date": None, "duration_days": None,
        "deadline": None, "eligible_countries": [], "eligible_note": None, "az_eligible": "unknown",
        "age_min": None, "age_max": None,
        "costs": {"accommodation_food": "unknown", "travel": "unknown",
                  "travel_limit_eur": None, "fee_eur": None, "fee_note": None},
        "spots_per_country": None, "spots_total": None, "organizer": None,
        "topics": [], "description": None, "detail": False,
    }


def set_dates(project, start, end):
    project["start_date"], project["end_date"] = iso(start), iso(end)
    if start and end and end >= start:
        project["duration_days"] = (end - start).days + 1


_FEE_AFTER = re.compile(
    r"(?:participation|contribution|registration|membership|administrative|application)\s+fee"
    r"[^.\n]{0,60}?(?:(?:€|eur\s?)\s*(\d{1,4})|(\d{1,4})\s*(?:€|eur))", re.I)
_FEE_BEFORE = re.compile(
    r"(?:(?:€|eur\s?)\s*(\d{1,4})|(\d{1,4})\s*(?:€|eur\w*))\s+"
    r"(?:participation|contribution|registration|membership|administrative)\s+fee", re.I)
_NO_FEE = re.compile(r"no (?:participation|contribution|registration) fee|free of charge|there is no fee", re.I)
_LIMIT = re.compile(r"up to\s*(?:€|eur\s?)\s*([\d.,]+)|up to\s*([\d.,]+)\s*(?:€|eur)", re.I)


def parse_costs(text):
    """Best-effort reading of a costs sentence; the AI step refines what stays 'unknown'."""
    low = (text or "").lower()
    costs = {"accommodation_food": "unknown", "travel": "unknown",
             "travel_limit_eur": None, "fee_eur": None, "fee_note": None}
    if re.search(r"(accommodation|food|meals|board|lodging)[^.]{0,60}(covered|provided|free|included)", low):
        costs["accommodation_food"] = "covered"
    if re.search(r"travel[^.]{0,60}reimburs|reimburs[^.]{0,40}travel", low):
        costs["travel"] = "reimbursed"
    elif re.search(r"(travel|flight)[^.]{0,40}(covered|paid|provided)", low):
        costs["travel"] = "covered"
    m = _LIMIT.search(low)
    if m:
        try:
            costs["travel_limit_eur"] = int(float((m.group(1) or m.group(2)).replace(",", "").rstrip(".")))
        except ValueError:
            pass
    fee = _FEE_AFTER.search(low) or _FEE_BEFORE.search(low)
    if fee:
        costs["fee_eur"] = int(fee.group(1) or fee.group(2))
    elif _NO_FEE.search(low):
        costs["fee_eur"] = 0
    return costs


def page_lines(html_text, drop=("script", "style", "noscript")):
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(list(drop)):
        tag.decompose()
    return [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]


def between(lines, start, stop):
    """Lines after the first `start` line up to the first line matching `stop`."""
    try:
        i = lines.index(start) + 1
    except ValueError:
        return []
    out = []
    for line in lines[i:]:
        if stop(line):
            break
        out.append(line)
    return out


def shorten(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


# Country-group wordings (as used by SALTO and Erasmus+ calls) that include the home country.
HOME_GROUPS = {
    "Azerbaijan": ("eastern partnership", "south caucasus", "neighbouring the eu",
                   "other countries in the world"),
}


def home_status(countries, home, complete=True, extra_text=""):
    """'yes' / 'no' / 'unknown' — can someone living in `home` apply?"""
    blob = (" ".join(countries) + " " + extra_text).lower()
    if home.lower() in blob or any(group in blob for group in HOME_GROUPS.get(home, ())):
        return "yes"
    if (countries or extra_text.strip()) and complete:
        return "no"
    return "unknown"
