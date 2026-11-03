"""Area / radius / niche / min-score options, the geocoder, and the scheduled-run gate."""
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import requests  # noqa: E402

from leadagent import fetch_options as fo  # noqa: E402
import check_auto_fetch  # noqa: E402

CITIES = [
    {"name": "Hamilton, ON", "lat": 43.2557, "lng": -79.8711},
    {"name": "St. John's, NL", "lat": 47.5615, "lng": -52.7126},
]
CFG = {
    "country": "CA",
    "cities": CITIES,
    "niches": ["dental clinic", "med spa", "physiotherapist"],
    "overpass": {"radius_km": 25.0},
    "min_score_to_report": 40,
}


def fake_geocoder(area, country):
    return {"name": area, "lat": 1.0, "lng": 2.0}


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._p = status, payload

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


class AreaTests(unittest.TestCase):
    def test_good_areas_pass_and_are_tidied(self):
        for raw, want in [("  Brampton,   ON ", "Brampton, ON"), ("L6T 3Y3", "L6T 3Y3"),
                          ("Saint-Laurent", "Saint-Laurent"), ("Montréal", "Montréal"),
                          ("O'Brien Rd (north)", "O'Brien Rd (north)"), ("Ｔｏｒｏｎｔｏ", "Toronto")]:
            self.assertEqual(fo.sanitize_area(raw), want)

    def test_blank_means_no_area(self):
        for raw in (None, "", "   ", "\t\n "):
            self.assertEqual(fo.sanitize_area(raw), "")

    def test_hostile_areas_are_refused(self):
        bad = ["Toronto; rm -rf /", "$(whoami)", "`id`", "a|b", "x && y", "<script>alert(1)</script>",
               "Toronto\nToronto", "ab\x00cd", "ab\x1b[31m", "../../etc/passwd" + "\\", "{{7*7}}", "a" * 81,
               "!!!", "---", "...", "‮evil", "emoji 😀", "a;b", "a\"b", "a%00b", "name=value&x=${IFS}"]
        for raw in bad:
            with self.assertRaises(fo.OptionError, msg=repr(raw)):
                fo.sanitize_area(raw)

    def test_non_text_is_refused(self):
        for raw in (5, ["a"], {"$gt": ""}, b"abc"):
            with self.assertRaises(fo.OptionError):
                fo.sanitize_area(raw)


class NumberTests(unittest.TestCase):
    def test_radius(self):
        self.assertEqual(fo.parse_radius(None, 25), 25.0)
        self.assertEqual(fo.parse_radius("", 25), 25.0)
        self.assertEqual(fo.parse_radius("10", 25), 10.0)
        self.assertEqual(fo.parse_radius("0.5".replace("0.5", "1"), 25), 1.0)
        for bad in ("0", "51", "-3", "abc", "nan", "inf", "-inf", "1e9", "0x10", "10km"):
            with self.assertRaises(fo.OptionError, msg=bad):
                fo.parse_radius(bad, 25)

    def test_min_score(self):
        self.assertEqual(fo.parse_min_score(None, 40), 40)
        self.assertEqual(fo.parse_min_score("0", 40), 0)
        self.assertEqual(fo.parse_min_score("100", 40), 100)
        for bad in ("-1", "101", "4.5", "x", "1e2", "NaN"):
            with self.assertRaises(fo.OptionError, msg=bad):
                fo.parse_min_score(bad, 40)


class NicheTests(unittest.TestCase):
    allowed = CFG["niches"]

    def test_empty_means_all(self):
        self.assertEqual(fo.parse_niches(None, self.allowed), [])
        self.assertEqual(fo.parse_niches(" , ", self.allowed), [])

    def test_known_niches_in_any_case_without_duplicates(self):
        self.assertEqual(fo.parse_niches("Med Spa, dental clinic,MED SPA", self.allowed), ["med spa", "dental clinic"])

    def test_unknown_niche_is_refused(self):
        for bad in ("roofer", "dental clinic,roofer", "'; drop table", "dental clinic;med spa"):
            with self.assertRaises(fo.OptionError, msg=bad):
                fo.parse_niches(bad, self.allowed)


class ResolveTests(unittest.TestCase):
    def test_configured_city_needs_no_lookup(self):
        boom = mock.Mock(side_effect=AssertionError("should not geocode"))
        for typed in ("hamilton", "Hamilton, ON", "HAMILTON ON", "st johns", "St. John's"):
            c = fo.resolve_area(typed, CFG, boom)
            self.assertIn(c["name"], ("Hamilton, ON", "St. John's, NL"))

    def test_unknown_area_is_geocoded(self):
        c = fo.resolve_area("Brampton", CFG, fake_geocoder)
        self.assertEqual((c["name"], c["lat"], c["lng"]), ("Brampton", 1.0, 2.0))

    def test_apply_options_without_area_keeps_rotation(self):
        cfg, pairs = fo.apply_options(CFG, area=None, radius=None, niches_csv=None, min_score=None)
        self.assertIsNone(pairs)
        self.assertEqual(cfg["overpass"]["radius_km"], 25.0)

    def test_apply_options_builds_one_pair_per_niche_and_never_mutates_input(self):
        before = json.dumps(CFG, sort_keys=True)
        cfg, pairs = fo.apply_options(CFG, area="Brampton", radius="12", niches_csv="med spa,dental clinic",
                                      min_score="55", geocoder=fake_geocoder)
        self.assertEqual([p[0] for p in pairs], ["med spa", "dental clinic"])
        self.assertTrue(all(p[1]["name"] == "Brampton" for p in pairs))
        self.assertEqual(cfg["overpass"]["radius_km"], 12.0)
        self.assertEqual(cfg["min_score_to_report"], 55)
        self.assertEqual(json.dumps(CFG, sort_keys=True), before)

    def test_filters_work_without_an_area(self):
        cfg, pairs = fo.apply_options(CFG, area=None, radius=None, niches_csv="med spa", min_score="60")
        self.assertIsNone(pairs)
        self.assertEqual(cfg["niches"], ["med spa"])
        self.assertEqual(cfg["min_score_to_report"], 60)


class GeocodeTests(unittest.TestCase):
    def test_success_is_restricted_to_the_country(self):
        s = mock.Mock()
        s.get.return_value = Resp(200, [{"lat": "43.7", "lon": "-79.7"}])
        out = fo.geocode("Brampton", "CA", s)
        self.assertEqual((out["lat"], out["lng"]), (43.7, -79.7))
        self.assertEqual(s.get.call_args.kwargs["params"]["countrycodes"], "ca")
        self.assertIn("User-Agent", s.get.call_args.kwargs["headers"])

    def test_every_failure_becomes_a_friendly_error(self):
        cases = [Resp(200, []), Resp(200, [{"nope": 1}]), Resp(200, ValueError("bad json")),
                 Resp(200, [{"lat": "x", "lon": "y"}]), Resp(429, None), Resp(503, None)]
        for resp in cases:
            s = mock.Mock()
            s.get.return_value = resp
            with self.assertRaises(fo.OptionError):
                fo.geocode("Nowhere", "CA", s)
        s = mock.Mock()
        s.get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(fo.OptionError):
            fo.geocode("Nowhere", "CA", s)


class GateTests(unittest.TestCase):
    on = {"autoFetch": True, "enabledCountries": {"US": False, "CA": True}}

    def test_manual_runs_always_go_ahead(self):
        for cfg in (None, {}, {"autoFetch": False}, self.on):
            self.assertTrue(check_auto_fetch.decide("workflow_dispatch", "ca", cfg)[0])

    def test_scheduled_runs_need_auto_fetch_and_the_country(self):
        d = check_auto_fetch.decide
        self.assertTrue(d("schedule", "ca", self.on)[0])
        self.assertFalse(d("schedule", "us", self.on)[0])                       # US switched off
        self.assertFalse(d("schedule", "ca", {**self.on, "autoFetch": False})[0])
        self.assertFalse(d("schedule", "ca", {"autoFetch": True})[0])           # missing countries
        self.assertFalse(d("schedule", "ca", None)[0])                          # CRM unreachable: fail closed
        self.assertFalse(d("schedule", "xx", self.on)[0])

    def test_only_a_real_true_counts(self):
        d = check_auto_fetch.decide
        for truthy in ("true", 1, "yes", [1], {"a": 1}):
            self.assertFalse(d("schedule", "ca", {"autoFetch": truthy, "enabledCountries": {"CA": True}})[0])
            self.assertFalse(d("schedule", "ca", {"autoFetch": True, "enabledCountries": {"CA": truthy}})[0])

    def test_unreachable_crm_skips_the_scheduled_run(self):
        env = {"EVENT_NAME": "schedule", "MARKET": "ca", "CRM_URL": "http://127.0.0.1:9", "CRM_INGEST_TOKEN": "t"}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "github_output"
            with mock.patch.dict(os.environ, {**env, "GITHUB_OUTPUT": str(out)}):
                self.assertEqual(check_auto_fetch.main(), 0)
            self.assertIn("proceed=false", out.read_text())

    def test_no_crm_settings_means_scheduled_runs_do_nothing(self):
        with mock.patch.dict(os.environ, {"EVENT_NAME": "schedule", "MARKET": "ca", "CRM_URL": "", "CRM_INGEST_TOKEN": ""}):
            self.assertIsNone(check_auto_fetch.read_config())


class CommandLineTests(unittest.TestCase):
    """run.py itself: bad options stop it before anything is fetched."""

    def run_py(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "run.py"), "--config", str(ROOT / "config-ca.yaml"), *args],
                              capture_output=True, text=True, timeout=60)

    def test_bad_options_exit_with_code_2_and_a_clear_message(self):
        for args in (["--area", "x; rm -rf /"], ["--radius-km", "999", "--area", "Toronto"], ["--niches", "roofer"],
                     ["--min-score", "500"]):
            r = self.run_py(*args)
            self.assertEqual(r.returncode, 2, (args, r.stderr))
            self.assertIn("Cannot run with those options", r.stderr)


class OneThousandHostileInputs(unittest.TestCase):
    """1,000 random and hand-made nasty strings: none may crash, and every accepted one must be safe."""

    def test_sanitize_never_crashes_and_only_returns_safe_text(self):
        rng = random.Random(1000)
        nasty = ["; ", "| ", "&& ", "$(", "`", "\n", "\r", "\x00", "<", ">", "{{", "}}", "\\", '"', "%", "😀", "‮",
                 "​", "../", "'--", "${IFS}", "\t"]
        accepted = 0
        for i in range(1000):
            kind = i % 4
            if kind == 0:
                s = "".join(rng.choice(string.printable) for _ in range(rng.randint(0, 120)))
            elif kind == 1:
                s = "Toronto" + "".join(rng.choice(nasty) for _ in range(rng.randint(1, 4))) + "ON"
            elif kind == 2:
                s = "".join(chr(rng.randint(0, 0x2FFF)) for _ in range(rng.randint(1, 60)))
            else:
                s = rng.choice(["Hamilton", "L6T 3Y3", "St. John's", "Saint-Laurent", "Kitchener, ON"]) + " " * rng.randint(0, 5)
            try:
                out = fo.sanitize_area(s)
            except fo.OptionError:
                continue
            accepted += 1
            self.assertLessEqual(len(out), fo.MAX_AREA_LEN)
            self.assertFalse(any(c in out for c in ';|&$`<>{}\\"%\n\r\x00'), repr(s))
        self.assertGreater(accepted, 100)  # the generator really does produce valid names too

    def test_numbers_and_niches_never_crash(self):
        rng = random.Random(7)
        junk = ["", " ", "nan", "inf", "-0", "1e999", "0x1", "９", "１０", "1_0", "10 ", "\x00", "💥", "9" * 400, "-" * 50]
        for _ in range(500):
            v = rng.choice(junk) if rng.random() < .7 else str(rng.uniform(-1e6, 1e6))
            for fn in (lambda x: fo.parse_radius(x, 25), lambda x: fo.parse_min_score(x, 40),
                       lambda x: fo.parse_niches(x, CFG["niches"])):
                try:
                    fn(v)
                except fo.OptionError:
                    pass


if __name__ == "__main__":
    unittest.main()
