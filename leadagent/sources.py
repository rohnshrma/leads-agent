"""
Data sources for US business discovery - FREE, NO API KEY, NO CREDIT CARD.

Two keyless sources, either of which runs at zero cost forever:

1. OverpassSource (recommended default) - OpenStreetMap via the Overpass API.
   Plain HTTPS + JSON, no key, no account, no billing. Data is ODbL: yours
   to keep and use with attribution. Best for businesses with PREMISES
   (dentists, gyms, driving schools, auto shops). Weak for service-area
   trades (roofers, plumbers) who have no storefront mapped.

2. OvertureSource - Overture Maps Foundation "places" theme, read straight
   from public cloud GeoParquet with DuckDB. No key, no account, no billing.
   ~76M POIs conflated from Meta + Microsoft, so it covers service-area
   trades that OSM misses. Licence CDLA-Permissive-2.0: the output is fully
   yours, storable and resellable. Needs DuckDB's httpfs extension, which
   downloads on first run.

3. GooglePlacesSource - kept for completeness only. Google requires a
   BILLING ACCOUNT (a credit card) on the project even to use its free
   tier, so it is not a free option in the sense that matters here.

Neither free source carries ratings or review counts. The scorer therefore
uses different credibility signals - see audit.py.
"""

from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Iterable

import requests

from .safeurl import USER_AGENT


class SearchFailed(RuntimeError):
    """A search failed on every mirror. Recorded in the run summary; never treated as "0 results"."""


class DeadlineReached(RuntimeError):
    """The run's time limit is up: stop starting new requests and post what was found."""


# --------------------------------------------------------------------
# Common record shape
# --------------------------------------------------------------------
@dataclass
class Business:
    source: str
    source_id: str                 # place_id (Google) or GERS id (Overture)
    name: str = ""
    category: str = ""
    address: str = ""
    city_query: str = ""
    niche_query: str = ""
    phone: str = ""
    website: str = ""
    rating: float | None = None
    review_count: int | None = None
    business_status: str = ""
    maps_url: str = ""
    lat: float | None = None
    lng: float | None = None
    email: str = ""              # some OSM/Overture records carry one
    confidence: float | None = None   # Overture: how sure the place exists
    source_count: int | None = None   # how many datasets agreed it exists
    brand: str = ""                   # OSM brand tag: set for chains and franchises
    website_inferred: bool = False    # website guessed from the email's own domain
    google_place_id: str = ""         # from the optional Google check (place IDs may be stored)
    google_status: str = ""           # matched | no_match | not_checked | error ("" = check off)
    phone_status: str = ""            # found | missing | google_live (phone is shown live from Google, never stored)
    fetched_at: str = ""              # when this run saw the business (UTC, ISO)
    from_google: bool = False         # the record came from Google Places: its fields are held in memory only
    # filled in later by the auditor
    audit: dict = field(default_factory=dict)
    opportunity_score: int = 0
    reasons: list = field(default_factory=list)
    lead_type: str = ""

    def as_row(self) -> dict:
        d = asdict(self)
        a = d.pop("audit") or {}
        d["reasons"] = " | ".join(d.get("reasons") or [])
        for k in (
            "final_url", "http_status", "load_seconds", "https",
            "mobile_friendly", "platform", "page_kb", "title",
            "has_meta_description", "copyright_year",
            "verdict",
        ):
            d[f"site_{k}"] = a.get(k, "")
        return d


# --------------------------------------------------------------------
# Google Places API (New)
# --------------------------------------------------------------------
class GooglePlacesSource:
    ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

    # Every field here is needed; websiteUri/phone/rating put the call in
    # the Enterprise SKU, which is where the 1,000 free monthly requests are.
    FIELD_MASK = ",".join([
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.primaryTypeDisplayName",
        "places.businessStatus",
        "places.googleMapsUri",
        "places.location",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "nextPageToken",
    ])

    def __init__(self, api_key: str, max_places: int = 20):
        if not api_key:
            raise RuntimeError(
                "No Google Maps API key. Set the env var named in "
                "config.yaml -> google_api_key_env, or switch "
                "source: \"overture\"."
            )
        self.api_key = api_key
        self.max_places = min(int(max_places), 20)

    def search(self, niche: str, city: dict) -> list[Business]:
        body = {
            "textQuery": f"{niche} in {city['name']}",
            "pageSize": self.max_places,
            "regionCode": "US",
            "includePureServiceAreaBusinesses": True,
        }
        if city.get("lat") is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": city["lat"], "longitude": city["lng"]},
                    "radius": 35000.0,
                }
            }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self.FIELD_MASK,
        }
        r = requests.post(self.ENDPOINT, json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Places API {r.status_code}: {r.text[:400]}")

        out = []
        for p in r.json().get("places", []):
            loc = p.get("location") or {}
            out.append(Business(
                source="google",
                source_id=p.get("id", ""),
                name=(p.get("displayName") or {}).get("text", ""),
                category=(p.get("primaryTypeDisplayName") or {}).get("text", ""),
                address=p.get("formattedAddress", ""),
                city_query=city["name"],
                niche_query=niche,
                phone=p.get("nationalPhoneNumber", ""),
                website=p.get("websiteUri", "") or "",
                rating=p.get("rating"),
                review_count=p.get("userRatingCount"),
                business_status=p.get("businessStatus", ""),
                maps_url=p.get("googleMapsUri", ""),
                lat=loc.get("latitude"),
                lng=loc.get("longitude"),
            ))
        return out


# --------------------------------------------------------------------
# OpenStreetMap via Overpass API - free, keyless, no billing
# --------------------------------------------------------------------
class OverpassSource:
    """
    Query OpenStreetMap for businesses in a bbox.

    No API key and no account. Public instances are donated infrastructure,
    so this class is a polite citizen: it identifies itself, sleeps between
    calls, and falls back across mirrors rather than hammering one.
    """

    MIRRORS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]
    # On a timeout or a busy answer (429/502/503/504) the same mirror is retried after these pauses
    # (plus up to 25% jitter) before moving to the next mirror.
    BACKOFF = (2.0, 5.0, 12.0)
    RETRY_STATUS = frozenset({429, 502, 503, 504})
    MAX_RETRY_AFTER = 60.0
    QUERY_TIMEOUT = 60          # the [timeout:] inside the query ...
    HTTP_TIMEOUT = 70           # ... and the HTTP wait: always a little longer, never shorter
    MAX_CONCURRENT = 2          # the public mirrors are donated; never more than two requests at once
    _gate = threading.BoundedSemaphore(2)

    def __init__(self, max_places: int = 100, pause: float = 2.0,
                 radius_km: float = 25.0, mirrors: list[str] | None = None,
                 tile_km: float = 25.0, post=None, sleep=None, deadline: float | None = None):
        self.max_places = int(max_places)
        self.pause = float(pause)
        self.radius_km = float(radius_km)
        self.mirrors = list(mirrors or self.MIRRORS)
        self.tile_km = max(5.0, float(tile_km))
        self._post = post or requests.post
        self._sleep = sleep or time.sleep
        self.deadline = deadline            # time.monotonic() value after which no new request starts
        self._last_call = 0.0
        self.failures: list[dict] = []      # {"type", "area", "error"} for every search that failed
        self.requests_made = 0

    @staticmethod
    def _bbox(lat: float, lng: float, km: float):
        import math
        dlat = km / 111.0
        dlng = km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        return (lat - dlat, lng - dlng, lat + dlat, lng + dlng)

    def _throttle(self):
        wait = self.pause - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _query(self, niche: str, city: dict, km: float | None = None) -> str:
        from .osm_tags import tags_for
        s_, w_, n_, e_ = self._bbox(city["lat"], city["lng"], km if km is not None else self.radius_km)
        bbox = f"{s_:.5f},{w_:.5f},{n_:.5f},{e_:.5f}"
        parts = []
        for tag in tags_for(niche):
            for kind in ("node", "way"):
                parts.append(f'  {kind}[{tag}]({bbox});')
        body = "\n".join(parts)
        # "out center tags" gives one point per feature plus its tags.
        return (
            f"[out:json][timeout:{self.QUERY_TIMEOUT}];\n(\n{body}\n);\n"
            f"out center tags {self.max_places};"
        )

    @staticmethod
    def _first(tags: dict, *keys: str) -> str:
        for k in keys:
            v = (tags.get(k) or "").strip()
            if v:
                return v
        return ""

    @staticmethod
    def _address(tags: dict) -> str:
        num = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        line1 = " ".join(x for x in (num, street) if x)
        city = tags.get("addr:city", "")
        # Canadian addresses are often tagged addr:province instead of addr:state.
        state = tags.get("addr:state", "") or tags.get("addr:province", "")
        post = tags.get("addr:postcode", "")
        tail = f"{city}, {state} {post}".strip().strip(",").strip()
        return ", ".join(x for x in (line1, tail) if x)

    def parse(self, payload: dict, niche: str, city: dict) -> list["Business"]:
        out = []
        for el in payload.get("elements", []):
            tags = el.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue           # unnamed features are not sellable leads
            centre = el.get("center") or {}
            lat = el.get("lat", centre.get("lat"))
            lng = el.get("lon", centre.get("lon"))
            website = self._first(
                tags, "website", "contact:website", "url", "contact:url")
            phone = self._first(
                tags, "phone", "contact:phone", "contact:mobile", "telephone")
            email = self._first(tags, "email", "contact:email")
            brand = self._first(tags, "brand", "brand:wikidata", "brand:en")
            category = self._first(
                tags, "amenity", "shop", "office", "craft", "healthcare",
                "leisure").replace("_", " ")
            osm_id = f'{el.get("type","node")}/{el.get("id","")}'
            out.append(Business(
                source="osm",
                source_id=osm_id,
                name=name,
                category=category,
                address=self._address(tags),
                city_query=city["name"],
                niche_query=niche,
                phone=phone,
                website=website,
                email=email,
                brand=brand,
                business_status="OPERATIONAL",
                maps_url=f"https://www.openstreetmap.org/{osm_id}",
                lat=lat, lng=lng,
                source_count=1,
            ))
        return out

    def _tiles(self, city: dict) -> list[tuple[float, float, float]]:
        """Centres (lat, lng, half-side km) of the smaller squares a large area is split into."""
        import math
        side = 2 * self.radius_km
        n = max(1, min(4, math.ceil(side / self.tile_km)))     # at most 4 x 4 = 16 queries per type
        half = side / n / 2
        out = []
        for i in range(n):
            for j in range(n):
                dy = -self.radius_km + half + i * 2 * half
                dx = -self.radius_km + half + j * 2 * half
                lat = city["lat"] + dy / 111.0
                lng = city["lng"] + dx / (111.0 * max(math.cos(math.radians(city["lat"])), 0.01))
                out.append((lat, lng, half))
        return out

    def _request(self, q: str) -> dict:
        """One query, across the mirrors, with retries. Returns the JSON or raises SearchFailed."""
        last = "no mirror tried"
        for url in self.mirrors:
            for attempt in range(len(self.BACKOFF) + 1):
                if self.deadline is not None and time.monotonic() >= self.deadline:
                    raise DeadlineReached("run time limit reached")
                self._throttle()
                wait = None
                try:
                    with self._gate:
                        self.requests_made += 1
                        r = self._post(url, data={"data": q}, timeout=self.HTTP_TIMEOUT,
                                       headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200:
                        try:
                            return r.json()
                        except ValueError:
                            last = "mirror answered with something that is not JSON"
                            break                      # a broken mirror: next one
                    last = f"HTTP {r.status_code}"
                    if r.status_code not in self.RETRY_STATUS:
                        break                          # e.g. 400/403: retrying will not help
                    ra = (getattr(r, "headers", None) or {}).get("Retry-After")
                    if ra:
                        try:
                            wait = min(float(ra), self.MAX_RETRY_AFTER)
                        except ValueError:
                            wait = None
                except requests.Timeout:
                    last = "timeout"
                except requests.RequestException as ex:
                    last = type(ex).__name__
                    break
                if attempt < len(self.BACKOFF):
                    base = self.BACKOFF[attempt]
                    self._sleep(max(wait, 0.0) if wait is not None else base + random.uniform(0, base * 0.25))
        raise SearchFailed(last)

    def search(self, niche: str, city: dict) -> list["Business"]:
        """All businesses of one type around one area. Raises SearchFailed when EVERY part failed."""
        merged: dict[str, "Business"] = {}
        ok = 0
        last = ""
        tiles = self._tiles(city)
        for lat, lng, half in tiles:
            q = self._query(niche, {"lat": lat, "lng": lng}, half)
            try:
                payload = self._request(q)
            except SearchFailed as ex:
                last = str(ex)
                continue
            ok += 1
            for b in self.parse(payload, niche, city):
                merged.setdefault(b.source_id, b)
        if ok == 0:
            self.failures.append({"type": niche, "area": city.get("name", ""), "error": last})
            raise SearchFailed(last)
        if ok < len(tiles):
            self.failures.append({"type": niche, "area": city.get("name", ""),
                                  "error": f"{len(tiles) - ok} of {len(tiles)} parts failed: {last}"})
        return list(merged.values())


# --------------------------------------------------------------------
# Overture Maps (free, storable)
# --------------------------------------------------------------------
class OvertureSource:
    """Query Overture's public GeoParquet with DuckDB over a bbox."""

    def __init__(self, release: str = "2026-08-19.0", max_places: int = 100, cache_dir: str | None = None,
                 query=None):
        self.release = release
        self.max_places = int(max_places)
        self.cache_dir = cache_dir          # open data only (Overture's licence allows keeping it)
        self._query_fn = query              # injected in tests so nothing is downloaded
        self._con = None

    def _con_get(self):
        if self._con is None:
            import duckdb
            con = duckdb.connect()
            con.execute("INSTALL spatial; LOAD spatial;")
            con.execute("INSTALL httpfs; LOAD httpfs;")
            con.execute("SET s3_region='us-west-2';")
            self._con = con
        return self._con

    @staticmethod
    def _bbox(lat: float, lng: float, km: float = 35.0):
        import math
        dlat = km / 111.0
        dlng = km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        return lng - dlng, lat - dlat, lng + dlng, lat + dlat

    def _cache_path(self, niche: str, city: dict):
        import hashlib
        from pathlib import Path
        key = f'{self.release}|{niche.lower()}|{round(city["lat"], 2)}|{round(city["lng"], 2)}|{self.max_places}'
        return Path(self.cache_dir) / (hashlib.sha1(key.encode()).hexdigest()[:20] + ".json")

    def search(self, niche: str, city: dict) -> list[Business]:
        """Rows for one niche around one area. Repeat runs read the cache instead of the network."""
        import json
        path = self._cache_path(niche, city) if self.cache_dir else None
        if path is not None and path.exists():
            try:
                return self._to_businesses(json.loads(path.read_text(encoding="utf-8")), niche, city)
            except (ValueError, OSError):
                pass                                    # a damaged cache file is just a miss
        rows = (self._query_fn or self._query_rows)(niche, city)
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(rows), encoding="utf-8")
            except OSError:
                pass
        return self._to_businesses(rows, niche, city)

    def _query_rows(self, niche: str, city: dict) -> list[dict]:
        con = self._con_get()
        xmin, ymin, xmax, ymax = self._bbox(city["lat"], city["lng"])
        path = (
            f"s3://overturemaps-us-west-2/release/{self.release}"
            "/theme=places/type=place/*"
        )
        # Match the niche against the category and the name.
        terms = [t for t in niche.lower().split() if len(t) > 2]
        like = " OR ".join(
            ["lower(coalesce(basic_category,'')) LIKE ?"] * len(terms)
            + ["lower(coalesce(names.primary,'')) LIKE ?"] * len(terms)
        )
        params = [f"%{t}%" for t in terms] * 2
        sql = f"""
            SELECT id,
                   names.primary            AS name,
                   basic_category           AS category,
                   addresses[1].freeform    AS street,
                   addresses[1].locality    AS locality,
                   addresses[1].region      AS region,
                   coalesce(websites[1],'') AS website,
                   coalesce(phones[1],'')   AS phone,
                   coalesce(emails[1],'')   AS email,
                   confidence,
                   len(coalesce(sources,[])) AS source_count,
                   ST_X(geometry) AS lng, ST_Y(geometry) AS lat
            FROM read_parquet('{path}', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN {xmin} AND {xmax}
              AND bbox.ymin BETWEEN {ymin} AND {ymax}
              AND coalesce(operating_status,'open') = 'open'
              AND coalesce(confidence, 0) >= 0.5
              AND ({like})
            LIMIT {self.max_places}
        """
        rows = con.execute(sql, params).fetchall()
        cols = [c[0] for c in con.description]
        return [dict(zip(cols, row)) for row in rows]

    @staticmethod
    def _to_businesses(rows: list[dict], niche: str, city: dict) -> list[Business]:
        out = []
        for d in rows:
            addr = ", ".join(
                x for x in (d.get("street"), d.get("locality"), d.get("region")) if x
            )
            out.append(Business(
                source="overture",
                source_id=str(d.get("id", "")),
                name=d.get("name") or "",
                category=d.get("category") or "",
                address=addr,
                city_query=city["name"],
                niche_query=niche,
                phone=d.get("phone") or "",
                website=d.get("website") or "",
                email=d.get("email") or "",
                business_status="OPERATIONAL",
                lat=d.get("lat"),
                lng=d.get("lng"),
                confidence=d.get("confidence"),
                source_count=d.get("source_count"),
            ))
        return out


def build_source(cfg: dict):
    """
    Pick a source from config. The two free ones need no key and no card.

      "osm"      OpenStreetMap / Overpass  - zero setup, works immediately
      "overture" Overture Maps + DuckDB    - far better coverage
      "google"   Google Places             - needs a BILLING ACCOUNT
    """
    kind = (cfg.get("source") or "osm").lower()
    mx = cfg.get("max_places_per_query", 40)

    if kind in ("osm", "openstreetmap", "overpass"):
        o = cfg.get("overpass", {}) or {}
        return OverpassSource(
            max_places=mx,
            pause=o.get("pause_seconds", 2.0),
            radius_km=o.get("radius_km", 25.0),
            mirrors=o.get("mirrors") or None,
            tile_km=o.get("tile_km", 25.0),
        )

    if kind == "overture":
        return build_overture(cfg)

    if kind == "google":
        key = os.environ.get(
            cfg.get("google_api_key_env", "GOOGLE_MAPS_API_KEY"), "")
        return GooglePlacesSource(key, min(mx, 20))

    raise RuntimeError(
        f'Unknown source "{kind}". Use "osm" (free, no setup), '
        '"overture" (free, better coverage) or "google" (needs billing).'
    )


def build_overture(cfg: dict) -> "OvertureSource":
    o = cfg.get("overture") or {}
    return OvertureSource(cfg.get("overture_release", "2026-08-19.0"), o.get("max_places", 100),
                          cache_dir=o.get("cache_dir", "cache/overture"))


def check_source(cfg: dict) -> int:
    """`python3 run.py --check-source` - verify connectivity before a real run."""
    kind = (cfg.get("source") or "osm").lower()
    city = (cfg.get("cities") or [{}])[0]
    niche = (cfg.get("niches") or ["dental clinic"])[0]
    print(f'source: {kind}\nprobe : "{niche}" in {city.get("name","?")}\n')
    try:
        src = build_source(cfg)
        got = src.search(niche, city)
    except Exception as ex:
        print(f"FAILED: {type(ex).__name__}: {ex}")
        if kind == "overture":
            print("\nOverture needs DuckDB's httpfs extension, which it "
                  "downloads on first use.\nIf your network blocks that, "
                  'switch to source: "osm" in config.yaml.')
        if kind in ("osm", "overpass"):
            print("\nOverpass mirrors are sometimes overloaded. Wait a "
                  "minute and retry;\nif it keeps failing, try "
                  'source: "overture".')
        return 1

    print(f"OK - {len(got)} businesses returned")
    withsite = sum(1 for b in got if b.website)
    withphone = sum(1 for b in got if b.phone)
    print(f"  with a website listed : {withsite}")
    print(f"  with no website       : {len(got) - withsite}   <- your leads")
    print(f"  with a phone number   : {withphone}")
    for b in got[:5]:
        flag = "SITE" if b.website else "NONE"
        print(f"  [{flag}] {b.name[:44]:<44} {b.phone or '(no phone)'}")
    return 0
