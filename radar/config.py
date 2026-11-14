import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "projects.json"

DEFAULT_PROFILE = {
    "country": "Azerbaijan",
    "birth_year": None,
    "english_level": "B1",
    "youth_work_experience": False,
    "interests": [],
    "preferred_duration_days": [5, 14],
    "max_fee_eur": 50,
    # Assumption to verify before travelling: entry rules change.
    "visa_free_countries": ["Türkiye", "Georgia"],
    "notify_min_score": 50,
}


def load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_profile():
    raw = os.environ.get("PROFILE_JSON")
    path = ROOT / "profile.json"
    if raw:
        data = json.loads(raw)
    elif path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    return {**DEFAULT_PROFILE, **data}
