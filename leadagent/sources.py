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
import time
from dataclasses import dataclass, field, asdict
from typing import Iterable

import requests


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
            "has_meta_description", "copyright_year", "emails_found",
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
        "https://overpass.osm.jp/api/interpreter",
    ]

    def __init__(self, max_places: int = 40, pause: float = 2.0,
                 radius_km: float = 25.0):
        self.max_places = int(max_places)
        self.pause = float(pause)
        self.radius_km = float(radius_km)
        self._last_call = 0.0

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

    def _query(self, niche: str, city: dict) -> str:
        from .osm_tags import tags_for
        s_, w_, n_, e_ = self._bbox(city["lat"], city["lng"], self.radius_km)
        bbox = f"{s_:.5f},{w_:.5f},{n_:.5f},{e_:.5f}"
        parts = []
        for tag in tags_for(niche):
            for kind in ("node", "way"):
                parts.append(f'  {kind}[{tag}]({bbox});')
        body = "\n".join(parts)
        # "out center tags" gives one point per feature plus its tags.
        return (
            f"[out:json][timeout:90];\n(\n{body}\n);\n"
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
        state = tags.get("addr:state", "")
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
                business_status="OPERATIONAL",
                maps_url=f"https://www.openstreetmap.org/{osm_id}",
                lat=lat, lng=lng,
                source_count=1,
            ))
        return out

    def search(self, niche: str, city: dict) -> list["Business"]:
        q = self._query(niche, city)
        last_err = None
        for url in self.MIRRORS:
            self._throttle()
            try:
                r = requests.post(
                    url, data={"data": q}, timeout=120,
                    headers={"User-Agent": (
                        "WebiGeeksLeadAgent/1.0 (contact: "
                        "rohan@webigeeksdigital.com)")},
                )
                if r.status_code == 200:
                    return self.parse(r.json(), niche, city)
                # 429/504 mean the instance is busy - try the next mirror.
                last_err = f"{url} -> HTTP {r.status_code}"
            except requests.RequestException as ex:
                last_err = f"{url} -> {type(ex).__name__}"
        raise RuntimeError(f"all Overpass mirrors failed ({last_err})")


# --------------------------------------------------------------------
# Overture Maps (free, storable)
# --------------------------------------------------------------------
class OvertureSource:
    """Query Overture's public GeoParquet with DuckDB over a bbox."""

    def __init__(self, release: str = "2026-08-19.0", max_places: int = 20):
        self.release = release
        self.max_places = int(max_places)
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
        dlat = km / 111.0
        dlng = km / 85.0
        return lng - dlng, lat - dlat, lng + dlng, lat + dlat

    def search(self, niche: str, city: dict) -> list[Business]:
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
        out = []
        for row in rows:
            d = dict(zip(cols, row))
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
        )

    if kind == "overture":
        return OvertureSource(cfg.get("overture_release", "2026-08-19.0"), mx)

    if kind == "google":
        key = os.environ.get(
            cfg.get("google_api_key_env", "GOOGLE_MAPS_API_KEY"), "")
        return GooglePlacesSource(key, min(mx, 20))

    raise RuntimeError(
        f'Unknown source "{kind}". Use "osm" (free, no setup), '
        '"overture" (free, better coverage) or "google" (needs billing).'
    )


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
