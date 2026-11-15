import argparse
import os
import sys
import time
from datetime import date

from . import ai, telegram
from .config import load_env, load_profile
from .scoring import score
from .sources import SOURCES
from .store import Store
from .util import from_iso, log

AI_PAUSE_SECONDS = 4
MAX_ALERTS_PER_RUN = 8
REMIND_DAYS = 3


def _open(p, today):
    deadline = from_iso(p.get("deadline"))
    return not deadline or deadline >= today


def _same_call(p):
    """Key that matches one call listed by two sources."""
    return "".join(ch for ch in p["title"].lower() if ch.isalnum())[:40], p.get("start_date")


def collect(store, today, home):
    for name, source in SOURCES.items():
        try:
            items = source.collect(store.projects, today, home)
        except Exception as exc:
            log(f"{name}: collection failed — {type(exc).__name__}: {exc}")
            continue
        listed = {_same_call(p) for p in store.projects.values() if p["source"] != name}
        items = [p for p in items if p["url"] in store.projects
                 or (_same_call(p) not in listed and Store.fresh(p, today))]
        added = sum(store.upsert(item, today) for item in items)
        log(f"{name}: {added} new")


def analyze(store, today, home, limit):
    todo = [p for p in store.projects.values()
            if p.get("analysis") != "ai" and p.get("az_eligible") != "no" and _open(p, today)]
    if ai.enabled() and limit > 0:
        todo.sort(key=lambda p: (p.get("az_eligible") != "yes", p.get("deadline") or "9999"))
        done = failures = 0
        for p in todo:
            if done >= limit or failures >= 3:
                break
            try:
                text = SOURCES[p["source"]].text_for(p, home)
            except Exception as exc:
                log(f"could not read {p['url']} for analysis: {type(exc).__name__}")
                continue
            if not text:
                continue
            try:
                ai.apply(p, ai.analyze(p, text, home))
                done, failures = done + 1, 0
                time.sleep(AI_PAUSE_SECONDS)
            except ai.QuotaExceeded:
                log("no AI model is available right now (quota or overload); the rest waits for the next run")
                break
            except Exception as exc:
                failures += 1
                log(f"AI analysis failed for {p['url']}: {type(exc).__name__}: {exc}")
        log(f"AI analysed {done} of {len(todo)} waiting projects")
    else:
        log("AI is not configured (AI_API_KEY); using rule-based flashcards")
    for p in todo:
        if p.get("analysis") != "ai":
            p["analysis"] = "rules"
            p["flashcards"] = ai.fallback_cards(p)


def rescore(store, profile, today):
    for p in store.projects.values():
        p["score"] = score(p, profile, today)
        p["status"] = "open" if _open(p, today) else "expired"


def notify(store, profile, today):
    if not telegram.enabled():
        log("Telegram is not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID); no alerts sent")
        return
    panel = os.environ.get("PANEL_URL", "")
    live = [p for p in store.projects.values() if p["status"] == "open" and p["score"]["eligible"]]
    fresh = sorted((p for p in live if not p.get("notified_at")
                    and p["score"]["total"] >= profile["notify_min_score"]),
                   key=lambda p: -p["score"]["total"])
    sent = 0
    for p in fresh[:MAX_ALERTS_PER_RUN]:
        if telegram.send(*telegram.card(p, today, panel)):
            p["notified_at"] = today.isoformat()
            sent += 1
    waiting = len(fresh) - MAX_ALERTS_PER_RUN
    if waiting > 0 and sent:
        telegram.send(f"Daha {waiting} uyğun layihə növbədədir — növbəti yoxlamada göndəriləcək.")
    for p in live:
        deadline = from_iso(p.get("deadline"))
        if p.get("notified_at") and not p.get("reminded") and deadline \
                and 0 <= (deadline - today).days <= REMIND_DAYS and p["notified_at"] != today.isoformat():
            if telegram.send(*telegram.reminder(p, today)):
                p["reminded"] = True
    log(f"telegram: {sent} alerts sent")


def cmd_run(args):
    profile, store, today = load_profile(), Store.load(), date.today()
    home = profile["country"]
    if not args.offline:
        collect(store, today, home)
        analyze(store, today, home, args.ai_limit)
    rescore(store, profile, today)
    if not args.no_notify:
        notify(store, profile, today)
    store.prune(today)
    store.save(home_country=home, ai_enabled=ai.enabled(),
               profile_set=bool(profile.get("birth_year")))
    eligible = sum(1 for p in store.projects.values() if p["score"]["eligible"])
    log(f"saved {len(store.projects)} projects, {eligible} open to {home}")


def cmd_models(_args):
    for name in ai.list_models():
        print(name)


def cmd_test_telegram(_args):
    ok = telegram.enabled() and telegram.send("Layihə Radarı: Telegram bağlantısı işləyir.")
    print("sent" if ok else "failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    sys.exit(0 if ok else 1)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_env()
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="collect, analyse, score, notify")
    run.add_argument("--no-notify", action="store_true", help="do not send Telegram messages")
    run.add_argument("--offline", action="store_true", help="only re-score saved data (after a profile change)")
    run.add_argument("--ai-limit", type=int, default=30, help="max AI analyses per run")
    run.set_defaults(func=cmd_run)
    sub.add_parser("models", help="list models the AI key can use").set_defaults(func=cmd_models)
    sub.add_parser("test-telegram", help="send a test message").set_defaults(func=cmd_test_telegram)
    args = parser.parse_args()
    args.func(args)
