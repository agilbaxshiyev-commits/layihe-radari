import json
from datetime import datetime, timedelta, timezone

from .config import DATA_FILE
from .util import from_iso

VOLATILE = ("title", "deadline", "start_date", "end_date", "duration_days")
PROTECTED = ("id", "first_seen", "notified_at", "reminded")
KEEP_EXPIRED_DAYS = 30
EMPTY = (None, [], "unknown")


class Store:
    def __init__(self, projects, meta):
        self.projects = {p["url"]: p for p in projects}
        self.meta = meta

    @classmethod
    def load(cls):
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return cls(data.get("projects", []), data.get("meta", {}))
        return cls([], {})

    def upsert(self, new, today):
        """Insert a project or refresh a known one. Returns True when it is new."""
        prev = self.projects.get(new["url"])
        if prev is None:
            new.update(first_seen=today.isoformat(), last_seen=today.isoformat(),
                       notified_at=None, reminded=False)
            self.projects[new["url"]] = new
            return True
        # A listing row must not overwrite what a detail page or the AI already established.
        locked = (prev.get("detail") or prev.get("analysis") == "ai") and not new.get("detail")
        for key in (VOLATILE if locked else new.keys()):
            value = new.get(key)
            if key in PROTECTED or value in EMPTY:
                continue
            if key == "costs":
                prev["costs"].update({k: v for k, v in value.items() if v not in EMPTY})
            else:
                prev[key] = value
        prev["last_seen"] = today.isoformat()
        return False

    def prune(self, today):
        cutoff = today - timedelta(days=KEEP_EXPIRED_DAYS)

        def keep(p):
            deadline, end = from_iso(p.get("deadline")), from_iso(p.get("end_date"))
            if deadline:
                return deadline >= cutoff
            if end:
                return end >= today
            return (from_iso(p.get("last_seen")) or today) >= cutoff

        self.projects = {url: p for url, p in self.projects.items() if keep(p)}

    def save(self, **meta):
        self.meta.update(meta, updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        ordered = sorted(self.projects.values(),
                         key=lambda p: (-p.get("score", {}).get("total", 0), p.get("deadline") or "9999"))
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps({"meta": self.meta, "projects": ordered}, ensure_ascii=False, indent=1),
            encoding="utf-8")
