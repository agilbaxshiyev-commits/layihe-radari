import unittest
from datetime import date
from unittest import mock

from radar import ai
from radar.config import DEFAULT_PROFILE
from radar.scoring import score
from radar.store import Store
from radar.util import home_status, new_project, parse_costs, parse_range, set_dates, split_countries

TODAY = date(2026, 11, 14)


def project(**over):
    p = new_project("test", "https://example.org/p", "Test", "youth_exchange")
    p.update(az_eligible="yes", host_country="Poland", deadline="2026-12-10")
    set_dates(p, date(2027, 2, 1), date(2027, 2, 9))
    p["costs"].update(accommodation_food="covered", travel="reimbursed", fee_eur=0)
    p.update(over)
    return p


class Dates(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(parse_range("24 Feb – 4 Mar 2027"), (date(2027, 2, 24), date(2027, 3, 4)))
        self.assertEqual(parse_range("11-19 January 2027"), (date(2027, 1, 11), date(2027, 1, 19)))
        self.assertEqual(parse_range("28 December 2026 - 4 January 2027"),
                         (date(2026, 12, 28), date(2027, 1, 4)))
        self.assertEqual(parse_range("28 Dec – 4 Jan 2027"), (date(2026, 12, 28), date(2027, 1, 4)))
        self.assertEqual(parse_range("July 20 – 29, 2027"), (date(2027, 7, 20), date(2027, 7, 29)))
        self.assertEqual(parse_range("nothing here"), (None, None))


class Parsing(unittest.TestCase):
    def test_costs(self):
        c = parse_costs("Accommodation and meals covered · Travel reimbursed (up to €309)")
        self.assertEqual((c["accommodation_food"], c["travel"], c["travel_limit_eur"]),
                         ("covered", "reimbursed", 309))
        self.assertEqual(parse_costs("There is a participation fee of 30 EUR.")["fee_eur"], 30)
        self.assertEqual(parse_costs("No participation fee.")["fee_eur"], 0)
        self.assertIsNone(parse_costs("Nothing about money")["fee_eur"])

    def test_countries(self):
        self.assertEqual(split_countries("Bosnia and Herzegovina, Turkey and more"),
                         ["Bosnia and Herzegovina", "Türkiye"])
        self.assertEqual(home_status(["Italy", "Azerbaijan"], "Azerbaijan"), "yes")
        self.assertEqual(home_status(["Italy"], "Azerbaijan"), "no")
        self.assertEqual(home_status(["Italy"], "Azerbaijan", complete=False), "unknown")
        self.assertEqual(home_status([], "Azerbaijan", False, "Eastern Partnership countries"), "yes")


class Scoring(unittest.TestCase):
    def test_gates(self):
        self.assertFalse(score(project(az_eligible="no"), DEFAULT_PROFILE, TODAY)["eligible"])
        self.assertFalse(score(project(deadline="2026-11-01"), DEFAULT_PROFILE, TODAY)["eligible"])
        too_old = {**DEFAULT_PROFILE, "birth_year": 1990}
        self.assertFalse(score(project(age_min=18, age_max=30), too_old, TODAY)["eligible"])
        in_range = {**DEFAULT_PROFILE, "birth_year": 2000}
        self.assertTrue(score(project(age_min=18, age_max=30), in_range, TODAY)["eligible"])

    def test_ordering(self):
        exchange = score(project(), DEFAULT_PROFILE, TODAY)
        fellowship = score(project(type="other"), DEFAULT_PROFILE, TODAY)
        self.assertGreater(exchange["total"], fellowship["total"])
        cheap = score(project(), DEFAULT_PROFILE, TODAY)
        pricey = project()
        pricey["costs"]["fee_eur"] = 300
        self.assertGreater(cheap["total"], score(pricey, DEFAULT_PROFILE, TODAY)["total"])
        long_stay = project()
        set_dates(long_stay, date(2027, 2, 1), date(2027, 4, 30))
        self.assertGreater(cheap["fit"], score(long_stay, DEFAULT_PROFILE, TODAY)["fit"])
        for result in (exchange, fellowship):
            self.assertTrue(0 <= result["total"] <= 100)


class AiOutput(unittest.TestCase):
    def test_clean_drops_bad_values(self):
        result = ai.clean({
            "type": "hack", "deadline": "soon", "start_date": "2027-02-01", "fee_eur": "30",
            "age_min": 18, "applicant_eligible": "yes", "competition": "extreme",
            "documents": ["CV", 5, ""], "flashcards": [{"q": "Q?", "a": "A"}, {"q": 1}, "x"],
            "experience_required": "true",
        })
        self.assertEqual(result["type"], "other")
        self.assertIsNone(result["deadline"])
        self.assertEqual(result["start_date"], "2027-02-01")
        self.assertIsNone(result["fee_eur"])
        self.assertEqual(result["competition"], "medium")
        self.assertEqual(result["documents"], ["CV"])
        self.assertEqual(result["flashcards"], [{"q": "Q?", "a": "A"}])
        self.assertFalse(result["experience_required"])

    def test_apply_keeps_source_facts(self):
        p = project(deadline="2026-12-10", az_eligible="unknown")
        result = ai.clean({"deadline": "2027-01-01", "applicant_eligible": "yes", "fee_eur": 25,
                           "flashcards": []})
        ai.apply(p, result)
        self.assertEqual(p["deadline"], "2026-12-10")
        self.assertEqual(p["az_eligible"], "yes")
        self.assertEqual(p["costs"]["fee_eur"], 0)
        self.assertTrue(p["flashcards"])


class AiFallback(unittest.TestCase):
    def test_overloaded_model_falls_back_to_next(self):
        class Reply:
            def __init__(self, status, content=""):
                self.status_code, self.headers, self._content = status, {}, content

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": self._content}}]}

        asked = []

        def post(url, json, **_):
            asked.append(json["model"])
            if json["model"] == "big-flash":
                return Reply(503)
            return Reply(200, '{"applicant_eligible": "yes", "flashcards": []}')

        with mock.patch.object(ai, "_order", ["big-flash", "small-flash"]), \
                mock.patch.object(ai, "_down", set()), \
                mock.patch.object(ai.requests, "post", post), \
                mock.patch.dict("os.environ", {"AI_API_KEY": "test"}):
            result = ai.analyze(project(), "call text", "Azerbaijan")
            self.assertEqual(asked, ["big-flash", "small-flash"])
            self.assertEqual(result["model"], "small-flash")
            self.assertEqual(ai.model(), "small-flash")
            ai._down.add("small-flash")
            with self.assertRaises(ai.QuotaExceeded):
                ai.analyze(project(), "call text", "Azerbaijan")


class Storage(unittest.TestCase):
    def test_listing_does_not_overwrite_detail(self):
        store = Store([], {})
        full = project(detail=True, eligible_countries=["Italy", "Azerbaijan"])
        self.assertTrue(store.upsert(full, TODAY))
        row = project(detail=False, eligible_countries=["Italy"], az_eligible="unknown",
                      deadline="2026-12-20")
        self.assertFalse(store.upsert(row, TODAY))
        saved = store.projects["https://example.org/p"]
        self.assertEqual(saved["eligible_countries"], ["Italy", "Azerbaijan"])
        self.assertEqual(saved["az_eligible"], "yes")
        self.assertEqual(saved["deadline"], "2026-12-20")


if __name__ == "__main__":
    unittest.main()
