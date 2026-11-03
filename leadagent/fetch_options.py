"""
Options a person can choose when they start a fetch by hand from the CRM:
an area (city, suburb or postal code), a search radius, a subset of niches
and a minimum score.

Everything here treats its input as hostile. The values travel from a web form
through the CRM and GitHub Actions into this process, so they are checked
again here even though the CRM checks them first.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable

import requests

MAX_AREA_LEN = 80
MIN_RADIUS_KM = 1.0
MAX_RADIUS_KM = 50.0
MIN_SCORE_FLOOR = 0
MIN_SCORE_CEIL = 100

# Letters (any language), digits, space and the punctuation real place names use.
_AREA_OK = re.compile(r"^[\w .,'’()-]+$", re.UNICODE)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "WebiGeeksLeadAgent/1.0 (contact: rohan@webigeeksdigital.com)"


class OptionError(ValueError):
    """The person asked for something we will not run. The message is safe to show."""


def sanitize_area(text: str | None) -> str:
    """Return a cleaned area name, "" when none was given, or raise OptionError."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise OptionError("The area must be text.")
    # Normalise look-alike characters, then drop control characters before judging the text.
    s = unicodedata.normalize("NFKC", text).strip()
    if not s:
        return ""
    if any(unicodedata.category(c).startswith("C") for c in s):
        raise OptionError("The area contains characters that are not allowed.")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if len(s) > MAX_AREA_LEN:
        raise OptionError(f"The area is too long (most {MAX_AREA_LEN} characters).")
    if not _AREA_OK.match(s) or not re.search(r"[^\W_]", s):
        raise OptionError("The area may only use letters, numbers, spaces and , . ' - ( )")
    return s


def parse_radius(value, default: float) -> float:
    """Radius in km, clamped to a sane range. Blank means the config default."""
    if value is None or str(value).strip() == "":
        return float(default)
    try:
        r = float(str(value).strip())
    except ValueError:
        raise OptionError("The radius must be a number of kilometres.")
    if r != r or r in (float("inf"), float("-inf")):
        raise OptionError("The radius must be a number of kilometres.")
    if not (MIN_RADIUS_KM <= r <= MAX_RADIUS_KM):
        raise OptionError(f"The radius must be between {MIN_RADIUS_KM:g} and {MAX_RADIUS_KM:g} km.")
    return r


def parse_min_score(value, default: int) -> int:
    if value is None or str(value).strip() == "":
        return int(default)
    try:
        n = int(str(value).strip())
    except ValueError:
        raise OptionError("The minimum score must be a whole number.")
    if not (MIN_SCORE_FLOOR <= n <= MIN_SCORE_CEIL):
        raise OptionError(f"The minimum score must be between {MIN_SCORE_FLOOR} and {MIN_SCORE_CEIL}.")
    return n


def parse_niches(csv: str | None, allowed: list[str]) -> list[str]:
    """Comma-separated niches, each of which must already be in the config. [] = all of them."""
    if csv is None or not str(csv).strip():
        return []
    lookup = {a.strip().lower(): a for a in allowed}
    out: list[str] = []
    for part in str(csv).split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in lookup:
            raise OptionError(f'"{part.strip()[:40]}" is not one of the business types this market searches.')
        if lookup[key] not in out:
            out.append(lookup[key])
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’]", "", s.lower())).strip()


def match_configured_city(area: str, cities: list[dict]) -> dict | None:
    """An area typed as a city we already track ("hamilton" -> "Hamilton, ON") needs no geocoding."""
    want = _norm(area)
    if not want:
        return None
    for c in cities:
        full = _norm(c["name"])
        head = _norm(c["name"].split(",")[0])
        if want in (full, head):
            return c
    return None


def geocode(area: str, country: str, session=requests) -> dict:
    """Look the area up on OpenStreetMap's Nominatim, restricted to one country. Raises OptionError."""
    try:
        r = session.get(
            NOMINATIM,
            params={"q": area, "format": "jsonv2", "limit": 1, "countrycodes": country.lower()},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
    except requests.RequestException as ex:
        raise OptionError(f"Could not look up that area right now ({type(ex).__name__}). Try again in a minute.")
    if r.status_code != 200:
        raise OptionError(f"The place lookup answered HTTP {r.status_code}. Try again in a minute.")
    try:
        hits = r.json()
        lat, lng = float(hits[0]["lat"]), float(hits[0]["lon"])
    except (ValueError, KeyError, IndexError, TypeError):
        raise OptionError(f'No place called "{area}" was found in {country.upper()}. Try the city name or a postal code.')
    return {"name": area, "lat": lat, "lng": lng}


def resolve_area(area: str, cfg: dict, geocoder: Callable[[str, str], dict] = geocode) -> dict:
    """Turn a cleaned area string into {"name", "lat", "lng"}."""
    hit = match_configured_city(area, cfg.get("cities") or [])
    if hit:
        return dict(hit)
    return geocoder(area, cfg.get("country", "US"))


def apply_options(cfg: dict, *, area: str | None, radius, niches_csv: str | None, min_score,
                  geocoder: Callable[[str, str], dict] = geocode) -> tuple[dict, list[tuple[str, dict]] | None]:
    """
    Return (config with overrides applied, explicit search pairs or None).

    None means "no area given, rotate through the configured cities as usual".
    The incoming config is not modified.
    """
    cfg = {**cfg, "overpass": dict(cfg.get("overpass") or {})}
    clean_area = sanitize_area(area)
    niches = parse_niches(niches_csv, cfg.get("niches") or [])
    cfg["overpass"]["radius_km"] = parse_radius(radius, cfg["overpass"].get("radius_km", 25.0))
    cfg["min_score_to_report"] = parse_min_score(min_score, cfg.get("min_score_to_report", 40))

    if niches:
        cfg["niches"] = niches
    if not clean_area:
        return cfg, None
    city = resolve_area(clean_area, cfg, geocoder)
    return cfg, [(n, city) for n in cfg["niches"]]
