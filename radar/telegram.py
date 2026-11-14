import os
from html import escape as esc

import requests

from .scoring import TYPE_AZ
from .util import az_date, from_iso, log

API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 3900


def _cfg():
    return os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def enabled():
    return all(_cfg())


def send(text, buttons=None):
    token, chat = _cfg()
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u} for t, u in buttons]]}
    try:
        resp = requests.post(API.format(token=token), json=payload, timeout=30)
    except requests.RequestException as exc:
        # The exception text contains the request URL, and with it the bot token.
        log(f"telegram: request failed ({type(exc).__name__})")
        return False
    if not resp.ok:
        try:
            reason = resp.json().get("description", "")
        except ValueError:
            reason = ""
        log(f"telegram: HTTP {resp.status_code} {reason}")
    return resp.ok


def cost_text(costs):
    parts = []
    if costs["accommodation_food"] == "covered":
        parts.append("yaşayış və yemək ödənilir")
    elif costs["accommodation_food"] == "not_covered":
        parts.append("yaşayış və yemək ödənilmir")
    if costs["travel"] == "covered":
        parts.append("yol ödənilir")
    elif costs["travel"] == "reimbursed":
        limit = f" (€{costs['travel_limit_eur']}-dək)" if costs.get("travel_limit_eur") else ""
        parts.append("yol qaytarılır" + limit)
    elif costs["travel"] == "not_covered":
        parts.append("yol ödənilmir")
    return ", ".join(parts) or "məlum deyil — infopack-ə bax"


def fee_text(costs):
    fee = costs.get("fee_eur")
    if fee is None:
        return "qeyd olunmayıb"
    return "yoxdur" if fee == 0 else f"€{fee} — ödənişlidir"


def card(p, today, panel_url=""):
    score, costs, ai = p["score"], p["costs"], p.get("ai") or {}
    place = ", ".join(x for x in (p.get("city"), p.get("host_country")) if x) or "yer məlum deyil"
    head = [f"<b>{esc(p['title'])}</b>", f"{TYPE_AZ.get(p['type'], TYPE_AZ['other'])} · {esc(place)}"]
    if p.get("start_date"):
        days = f" ({p['duration_days']} gün)" if p.get("duration_days") else ""
        head.append(f"Tarix: {az_date(p['start_date'])} – {az_date(p.get('end_date'))}{days}")
    deadline = from_iso(p.get("deadline"))
    if deadline:
        head.append(f"Son tarix: {az_date(p['deadline'])} ({(deadline - today).days} gün qalıb)")
    head.append(f"Xərclər: {cost_text(costs)}")
    head.append(f"İştirak haqqı: {fee_text(costs)}")
    if costs.get("fee_note"):
        head.append(f"<i>{esc(costs['fee_note'])}</i>")
    head.append(f"\nBal: <b>{score['total']}/100</b> ({score['label']}) · "
                f"şans {score['chance']} · uyğunluq {score['fit']}")
    strongest = sorted((f for f in score["factors"] if f["d"]), key=lambda f: -abs(f["d"]))[:3]
    head += [f"{'+' if f['d'] > 0 else '−'}{abs(f['d'])} {esc(f['t'])}" for f in strongest]

    middle = []
    if ai.get("summary_az"):
        middle.append("\n" + esc(ai["summary_az"]))
    needs = (ai.get("documents") or []) + (ai.get("requirements") or [])
    if needs:
        middle.append("\n<b>Müraciət üçün lazımdır</b>")
        middle += [f"• {esc(n)}" for n in needs[:7]]

    cards = ["\n<b>Flashcard</b> (cavabı görmək üçün toxun)"]
    for c in (p.get("flashcards") or [])[:6]:
        cards.append(f"S: {esc(c['q'])}\nC: <tg-spoiler>{esc(c['a'])}</tg-spoiler>")

    text = "\n".join(head + middle + (cards if len(cards) > 1 else []))
    if len(text) > LIMIT:
        text = "\n".join(head + middle)
    if len(text) > LIMIT:
        text = "\n".join(head)
    buttons = [("Layihə səhifəsi", p["url"])]
    if panel_url:
        buttons.append(("Paneldə aç", f"{panel_url.rstrip('/')}/#{p['id']}"))
    return text, buttons


def reminder(p, today):
    left = (from_iso(p["deadline"]) - today).days
    when = "bu gün" if left == 0 else f"{left} gün sonra"
    text = (f"<b>Xatırlatma:</b> son müraciət tarixi {when} ({az_date(p['deadline'])})\n"
            f"{esc(p['title'])}\nBal: {p['score']['total']}/100")
    return text, [("Layihə səhifəsi", p["url"])]
