"""Heuristic 0-100 score. It ranks projects; it is not a measured acceptance probability."""
from .util import from_iso, norm_country

BASE = {"youth_exchange": 60, "esc_volunteering": 50, "training_course": 45, "other": 22}
TYPE_AZ = {"youth_exchange": "Gənclər mübadiləsi", "training_course": "Təlim kursu",
           "esc_volunteering": "ESC könüllülük", "other": "Digər proqram"}
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def _level(value):
    return LEVELS.index(value) if value in LEVELS else None


def _gate(text):
    return {"total": 0, "chance": 0, "fit": 0, "label": "Uyğun deyil", "eligible": False,
            "factors": [{"k": "gate", "d": 0, "t": text}]}


def _label(total):
    return "Yüksək" if total >= 70 else "Orta" if total >= 50 else "Aşağı" if total >= 30 else "Çox aşağı"


def score(p, profile, today):
    home = profile["country"]
    deadline, start = from_iso(p.get("deadline")), from_iso(p.get("start_date"))
    if p.get("az_eligible") == "no":
        return _gate(f"{home} iştirakçı ölkələr siyahısında yoxdur")
    if deadline and deadline < today:
        return _gate("Müraciət müddəti bitib")
    if not deadline and start and start < today:
        return _gate("Proqram artıq başlayıb")
    birth_year = profile.get("birth_year")
    if birth_year:
        oldest = (start or today).year - birth_year
        if p.get("age_min") and oldest < p["age_min"]:
            return _gate(f"Yaş həddi: minimum {p['age_min']}")
        if p.get("age_max") and oldest - 1 > p["age_max"]:
            return _gate(f"Yaş həddi: maksimum {p['age_max']}")

    ai = p.get("ai") or {}
    costs = p["costs"]
    kind = p.get("type") if p.get("type") in BASE else "other"
    factors = [{"k": "chance", "d": 0, "t": f"Başlanğıc bal: {TYPE_AZ[kind]} ({BASE[kind]})"}]
    points = {"chance": BASE[kind], "fit": 50}

    def add(kind_, delta, text):
        points[kind_] += delta
        factors.append({"k": kind_, "d": delta, "t": text})

    # --- chance of being selected ---
    if p.get("az_eligible") == "unknown":
        add("chance", -15, f"{home} üçün açıq olub-olmadığı dəqiq deyil")
    per_country = p.get("spots_per_country")
    if per_country:
        if per_country >= 5:
            add("chance", 8, f"Hər ölkədən {per_country} yer var")
        elif per_country >= 3:
            add("chance", 4, f"Hər ölkədən {per_country} yer var")
        else:
            add("chance", -8, f"Hər ölkədən cəmi {per_country} yer var")
    countries = len(p.get("eligible_countries") or [])
    if kind != "other" and 0 < countries <= 6:
        add("chance", 5, f"Cəmi {countries} ölkə iştirak edir, yerlər ölkələr arasında bölünür")
    elif countries > 20:
        add("chance", -8, f"{countries} ölkədən müraciət qəbul olunur")
    reason = f": {ai['competition_reason']}" if ai.get("competition_reason") else ""
    if ai.get("competition") == "low":
        add("chance", 10, "AI qiymətləndirməsi — rəqabət aşağıdır" + reason)
    elif ai.get("competition") == "high":
        add("chance", -15, "AI qiymətləndirməsi — rəqabət yüksəkdir" + reason)
    if ai.get("experience_required"):
        if profile.get("youth_work_experience"):
            add("chance", 8, "Tələb olunan gənclərlə iş təcrübən var")
        else:
            add("chance", -15, "Gənclərlə iş (youth worker) təcrübəsi tələb olunur")
    elif kind == "training_course" and not ai and not profile.get("youth_work_experience"):
        add("chance", -8, "Təlim kursları adətən gənclərlə işləyənlər üçün nəzərdə tutulur")
    need, have = _level(ai.get("required_english")), _level(profile.get("english_level"))
    if need is not None and have is not None:
        if have >= need:
            add("chance", 5, f"İngilis dili səviyyən ({profile['english_level']}) tələbə uyğundur")
        else:
            add("chance", -20, f"İngilis dili tələbi {ai['required_english']}, səninki {profile['english_level']}")
    host = norm_country(p.get("host_country") or "")
    visa_free = {norm_country(c).lower() for c in profile.get("visa_free_countries", [])}
    if host and host.lower() in visa_free:
        add("chance", 8, f"{host} üçün viza tələb olunmur (profilinə görə)")
    elif host and deadline and start and (start - deadline).days < 35:
        add("chance", -12, "Son tarixlə başlama arasında viza üçün vaxt azdır")
    if deadline and (deadline - today).days <= 1:
        add("chance", -10, "Müraciət üçün 1 gündən az vaxt qalıb")
    haystack = " ".join([p.get("title") or "", p.get("description") or "", " ".join(p.get("topics") or [])]).lower()
    matched = [i for i in profile.get("interests", []) if i and i.lower() in haystack]
    if matched:
        add("chance", 5, "Maraq sahənə uyğundur: " + ", ".join(matched[:3]))

    # --- fit with what you asked for ---
    low, high = profile["preferred_duration_days"]
    days = p.get("duration_days")
    if not days:
        add("fit", -5, "Müddət məlum deyil")
    elif low <= days <= high:
        add("fit", 25, f"Müddət {days} gün — istədiyin aralıqdadır")
    elif days < low:
        add("fit", 5, f"Müddət qısadır: {days} gün")
    elif days <= high + 7:
        add("fit", 8, f"Müddət {days} gün — istədiyindən bir az uzundur")
    else:
        add("fit", -25, f"Müddət uzundur: {days} gün")
    funded_by_rule = kind != "other" and costs["accommodation_food"] == costs["travel"] == "unknown"
    if funded_by_rule:
        add("fit", 8, "Erasmus+/ESC qaydalarına görə əsas xərclər adətən qarşılanır — infopack-də yoxla")
    if costs["accommodation_food"] == "covered":
        add("fit", 10, "Yaşayış və yemək ödənilir")
    elif costs["accommodation_food"] == "not_covered":
        add("fit", -25, "Yaşayış və yemək ödənilmir")
    if costs["travel"] == "covered":
        add("fit", 12, "Yol xərci ödənilir")
    elif costs["travel"] == "reimbursed":
        limit = f" (€{costs['travel_limit_eur']}-dək)" if costs.get("travel_limit_eur") else ""
        add("fit", 8, "Yol xərci sonradan qaytarılır" + limit)
    elif costs["travel"] == "not_covered":
        add("fit", -25, "Yol xərci ödənilmir")
    fee, max_fee = costs.get("fee_eur"), profile.get("max_fee_eur") or 0
    if fee == 0:
        add("fit", 5, "İştirak haqqı yoxdur")
    elif fee and fee <= max_fee:
        add("fit", -5, f"İştirak haqqı €{fee} — limitin (€{max_fee}) daxilindədir")
    elif fee:
        add("fit", -30, f"İştirak haqqı €{fee} — limitindən (€{max_fee}) çoxdur")

    chance = max(3, min(95, points["chance"]))
    fit = max(0, min(100, points["fit"]))
    total = round(0.65 * chance + 0.35 * fit)
    return {"total": total, "chance": chance, "fit": fit, "label": _label(total),
            "eligible": True, "factors": factors}
