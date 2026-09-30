"""
Render a one-page website mockup for a lead.

    render_mockup(row, out_dir)  ->  {"slug", "path", "niche", ...}

Output layout (static files, hostable anywhere for free):
    out_dir/
      assets/fonts/*.woff2          shared by every mockup
      <slug>/index.html             one self-contained page per lead
      index.html                    private gallery (noindex)

Safety by design: a mockup uses a business's real name and address, so every
page carries a visible "sample preview, not the official website" ribbon,
a noindex meta tag, and an unguessable slug. It never invents facts: see
niches.py for the placeholder rules.
"""

from __future__ import annotations

import hashlib
import html
import re
import shutil
from pathlib import Path
from urllib.parse import quote_plus

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .icons import svg
from .niches import FONTS, NICHES, niche_key_for

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
FONT_DIR = HERE / "static" / "fonts"

PH_RE = re.compile(r"\[\[(.+?)\]\]")

# Who the preview is "from". Overridable per call (run.py passes the config's outreach block).
DEFAULT_OWNER = {"company": "WebiGeeks Digital", "email": "rohan@webigeeksdigital.com"}


# ----------------------------------------------------------- lead -> context
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "business"


def parse_location(row: dict) -> tuple[str, str]:
    """Best-effort (city, state) from an agent row."""
    city, state = str(row.get("city") or "").strip(), str(row.get("state") or "").strip()
    addr = str(row.get("address") or "")
    m = re.search(r",\s*([^,]+),\s*([A-Z]{2})\s*\d{5}", addr)
    if m:
        city = city or m.group(1).strip()
        state = state or m.group(2)
    cq = str(row.get("city_query") or "")
    m = re.match(r"^(.*?)[,\s]+([A-Z]{2})$", cq.strip())
    if m:
        city = city or m.group(1).strip(" ,")
        state = state or m.group(2)
    elif cq and not city:
        city = cq.strip()
    return city, state


def fmt_phone(raw: str) -> tuple[str, str]:
    """('(864) 555-0100', '+18645550100'); unknown formats are passed through."""
    d = re.sub(r"\D", "", str(raw or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}", f"+1{d}"
    return (str(raw or "").strip(), "+" + d if d else "")


def _initials(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in {"the", "of", "and", "llc", "inc", "pllc", "pc", "p.c"}]
    return "".join(w[0] for w in words[:2]).upper() or name[:1].upper()


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_business(row: dict, niche_key: str) -> dict:
    name = str(row.get("name") or "Your Business").strip()
    city, state = parse_location(row)
    phone_display, phone_tel = fmt_phone(row.get("phone"))
    addr = str(row.get("address") or "").strip()
    lat, lng = _to_float(row.get("lat")), _to_float(row.get("lng"))
    has_map = lat is not None and lng is not None
    map_embed = directions = ""
    if has_map:
        d = 0.006
        map_embed = ("https://www.openstreetmap.org/export/embed.html?bbox="
                     f"{lng - d:.5f}%2C{lat - d * 0.6:.5f}%2C{lng + d:.5f}%2C{lat + d * 0.6:.5f}"
                     f"&layer=mapnik&marker={lat:.5f}%2C{lng:.5f}")
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lng:.6f}"
    elif addr or city:
        directions = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {addr or city}")
    city_state = ", ".join(x for x in (city, state) if x) or "your area"
    return {
        "name": name, "initials": _initials(name), "city": city or "your area", "state": state,
        "city_state": city_state, "address": addr, "phone": phone_display, "phone_tel": phone_tel,
        "email": str(row.get("email") or "").strip().split(",")[0].strip(),
        "lat": lat, "lng": lng, "has_map": has_map, "map_embed": map_embed, "directions": directions,
        "niche_key": niche_key, "name_has_cpa": bool(re.search(r"\bCPAs?\b", name, re.I)),
    }


def _fmt(s, b: dict) -> str:
    """Fill {city} {state} {city_state} {name} {phone}. Unknown braces are left alone."""
    if not isinstance(s, str):
        return s
    for k in ("city_state", "city", "state", "name", "phone"):
        s = s.replace("{" + k + "}", b.get(k, "") or "")
    return s


def _walk(obj, b):
    if isinstance(obj, str):
        return _fmt(obj, b)
    if isinstance(obj, tuple):
        return tuple(_walk(x, b) for x in obj)
    if isinstance(obj, list):
        return [_walk(x, b) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk(v, b) for k, v in obj.items()}
    return obj


def font_css(niche: dict, base: str = "../assets/fonts/") -> str:
    out = []
    for fam in niche["fonts"]:
        for weight, fname in FONTS[fam]:
            out.append(
                f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{weight};"
                f"font-display:swap;src:url({base}{fname}) format('woff2')}}")
    return "".join(out)


def pick_palette(niche: dict, seed: str) -> dict:
    n = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    return niche["palettes"][n % len(niche["palettes"])]


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)

    def rich(value):
        """Escape text, then turn [[placeholder]] into a visible 'add yours' chip."""
        safe = str(escape(value))
        return Markup(PH_RE.sub(lambda m: f'<span class="ph">{m.group(1)}</span>', safe))

    env.filters["rich"] = rich
    env.globals["icon"] = lambda name, cls="ic": Markup(svg(name, cls))
    return env


_ENV = None


def context_for(row: dict, niche_key: str, palette_index: int | None = None, owner: dict | None = None) -> dict:
    niche = NICHES[niche_key]
    b = build_business(row, niche_key)
    seed = str(row.get("source_id") or row.get("name") or "") + str(row.get("phone") or "")
    pal = niche["palettes"][palette_index] if palette_index is not None else pick_palette(niche, seed)
    n = _walk({k: v for k, v in niche.items() if k not in ("palettes", "keywords", "fonts")}, b)
    return {"b": b, "n": n, "pal": pal, "font_css": Markup(font_css(niche)), "niche_key": niche_key,
            "owner": {**DEFAULT_OWNER, **(owner or {})}}


def slug_for(row: dict) -> str:
    seed = str(row.get("source_id") or "") + str(row.get("name") or "") + str(row.get("phone") or "")
    return f"{_slug(str(row.get('name') or 'business'))}-{hashlib.sha1(seed.encode()).hexdigest()[:6]}"


def ensure_assets(out_dir: Path) -> None:
    dst = out_dir / "assets" / "fonts"
    dst.mkdir(parents=True, exist_ok=True)
    for f in FONT_DIR.glob("*"):
        if f.is_file() and not (dst / f.name).exists():
            shutil.copy2(f, dst / f.name)


def render_mockup(row: dict, out_dir, palette_index: int | None = None, owner: dict | None = None) -> dict | None:
    """Write out_dir/<slug>/index.html. Returns None if no template fits the niche."""
    global _ENV
    key = niche_key_for(row)
    if not key:
        return None
    _ENV = _ENV or _env()
    out_dir = Path(out_dir)
    ensure_assets(out_dir)
    ctx = context_for(row, key, palette_index, owner)
    html_text = _ENV.get_template(NICHES[key]["template"]).render(**ctx)
    slug = slug_for(row)
    target = out_dir / slug
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.html").write_text(html_text, encoding="utf-8")
    return {"slug": slug, "path": str(target / "index.html"), "niche": key,
            "business": ctx["b"]["name"], "palette": ctx["pal"]["name"]}


def write_gallery(items: list[dict], out_dir) -> Path:
    """A private index page listing every mockup built in this run."""
    out_dir = Path(out_dir)
    rows = "".join(
        f'<li><a href="{html.escape(i["slug"])}/">{html.escape(i["business"])}</a> '
        f'<span>{html.escape(NICHES[i["niche"]]["label"])} &middot; {html.escape(i["palette"])}</span></li>'
        for i in items)
    page = ("<!doctype html><meta charset=utf-8><meta name=robots content='noindex,nofollow'>"
            "<meta name=viewport content='width=device-width,initial-scale=1'><title>Mockups</title>"
            "<style>body{font:16px/1.5 system-ui;max-width:640px;margin:40px auto;padding:0 16px}"
            "li{margin:8px 0}li span{color:#666;font-size:14px}</style>"
            f"<h1>Mockups ({len(items)})</h1><ul>{rows}</ul>")
    p = out_dir / "index.html"
    p.write_text(page, encoding="utf-8")
    return p
