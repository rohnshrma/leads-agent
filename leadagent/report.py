"""Daily report: CSV to work from + an HTML page to read over chai."""

from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# US state -> IANA timezone, so the report can tell Rohan the local
# time at the prospect and whether it is legal/sensible to call now.
STATE_TZ = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Boise",
    "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
    "DC": "America/New_York",
}

IST = ZoneInfo("Asia/Kolkata")


def _state_of(addr: str) -> str:
    import re
    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", addr or "")
    return m.group(1) if m else ""


def call_window_ist(addr: str) -> str:
    """
    When Rohan (IST) should dial so it is business hours for the prospect.

    India is UTC+5:30, so the offset to any US state is a half-hour value.
    Rounding to whole hours would put every suggested call 30 minutes off,
    which matters when you are trying to catch an owner between jobs.
    This converts real datetimes instead.

    Federal telemarketing rules allow 8am-9pm in the RECIPIENT's local
    time; 9-11am and 2-4pm are when owners actually pick up.
    """
    st = _state_of(addr)
    tz = STATE_TZ.get(st)
    if not tz:
        return ""
    try:
        their_tz = ZoneInfo(tz)
        now_ist = datetime.now(IST)
        their_now = now_ist.astimezone(their_tz)

        def ist_str(local_hour: int) -> str:
            # Build that clock hour today in THEIR timezone, then read it
            # back on the IST clock. Handles DST and the :30 offset exactly.
            local_dt = their_now.replace(
                hour=local_hour, minute=0, second=0, microsecond=0)
            return local_dt.astimezone(IST).strftime("%H:%M")

        morning = f"{ist_str(9)}-{ist_str(11)}"
        afternoon = f"{ist_str(14)}-{ist_str(16)}"
        return (f"{st} - {their_now.strftime('%-I:%M %p')} there now. "
                f"Best: {morning} IST (their 9-11am). "
                f"Also {afternoon} IST (their 2-4pm, late night for you)")
    except Exception:
        return st


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("no new leads this run\n")
        return
    cols = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


BADGE = {
    "NO WEBSITE": ("#7f1d1d", "#fee2e2"),
    "SOCIAL ONLY": ("#7c2d12", "#ffedd5"),
    "BROKEN SITE": ("#831843", "#fce7f3"),
    "PLACEHOLDER": ("#78350f", "#fef3c7"),
    "WEAK SITE": ("#1e3a8a", "#dbeafe"),
    "HAS GOOD SITE": ("#334155", "#f1f5f9"),
}


def write_html(businesses: list, path: Path, meta: dict) -> None:
    e = html.escape
    cards = []
    for i, b in enumerate(businesses, 1):
        a = b.audit or {}
        fg, bg = BADGE.get(b.lead_type, ("#334155", "#f1f5f9"))
        contact = []
        if b.phone:
            tel = b.phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            contact.append(f'<a href="tel:{e(tel)}">{e(b.phone)}</a> '
                           f'<span class="mut">(call - best channel)</span>')
        else:
            contact.append('<span class="mut">No phone listed</span>')
        if a.get("emails_found"):
            contact.append(f'Email found: <b>{e(a["emails_found"])}</b>')
        if b.website:
            contact.append(f'Listed site: <a href="{e(b.website)}" '
                           f'target="_blank" rel="noopener">{e(b.website[:70])}</a>')
        if b.maps_url:
            contact.append(f'<a href="{e(b.maps_url)}" target="_blank" '
                           f'rel="noopener">Google listing</a>')

        win = call_window_ist(b.address)
        tech = []
        if a.get("platform"):
            tech.append(f"Built on {e(a['platform'])}")
        if a.get("load_seconds") is not None:
            tech.append(f"{a['load_seconds']}s load")
        if a.get("page_kb"):
            tech.append(f"{a['page_kb']} KB")
        if a.get("verdict") not in ("NO_WEBSITE", "SOCIAL_ONLY"):
            tech.append("HTTPS" if a.get("https") else "no HTTPS")

        cards.append(f"""
        <article class="card">
          <div class="top">
            <div>
              <span class="rank">#{i}</span>
              <h2>{e(b.name) or "(unnamed)"}</h2>
              <p class="sub">{e(b.category or b.niche_query)} &middot; {e(b.address)}</p>
            </div>
            <div class="right">
              <span class="badge" style="color:{fg};background:{bg}">{e(b.lead_type)}</span>
              <span class="score">{b.opportunity_score}</span>
            </div>
          </div>
          <ul class="why">{''.join(f'<li>{e(r)}</li>' for r in b.reasons)}</ul>
          <div class="contact">{'<br>'.join(contact)}</div>
          {f'<p class="win">{e(win)}</p>' if win else ''}
          {f'<p class="tech">{e(" &middot; ".join(tech))}</p>'.replace("&amp;middot;", "&middot;") if tech else ''}
          <p class="rev">{"★ " + str(b.rating) + f" ({b.review_count} reviews)" if b.rating else "no rating data"}</p>
        </article>""")

    counts = {}
    for b in businesses:
        counts[b.lead_type] = counts.get(b.lead_type, 0) + 1
    chips = "".join(
        f'<span class="chip">{e(k)}: <b>{v}</b></span>' for k, v in
        sorted(counts.items(), key=lambda kv: -kv[1])
    )

    src = (meta.get("source") or "").lower()
    if "osm" in src or "openstreetmap" in src:
        # ODbL requires attribution when you use or publish this data.
        attribution = (
            'Business data &copy; OpenStreetMap contributors, '
            '<a href="https://opendatacommons.org/licenses/odbl/" '
            'target="_blank" rel="noopener">ODbL</a>.')
    elif "overture" in src:
        attribution = (
            'Business data &copy; Overture Maps Foundation, '
            'CDLA-Permissive-2.0.')
    elif "google" in src:
        attribution = "Business data from Google. Not for redistribution."
    else:
        attribution = f"Source: {html.escape(meta.get('source',''))}."

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Lead Run {e(meta.get('date',''))}</title>
<style>
  :root {{
    --bg:#f8fafc; --card:#fff; --ink:#0f172a; --mut:#64748b;
    --line:#e2e8f0; --accent:#1d4ed8;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:#0b1120; --card:#111a2e; --ink:#e8eefc; --mut:#94a3b8;
      --line:#1e293b; --accent:#7ba2ff;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#0b1120; --card:#111a2e; --ink:#e8eefc; --mut:#94a3b8;
    --line:#1e293b; --accent:#7ba2ff;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    padding:0 16px 64px}}
  header{{max-width:920px;margin:0 auto;padding:32px 0 8px}}
  h1{{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}}
  .meta{{color:var(--mut);font-size:13.5px;margin:0 0 14px}}
  .chip{{display:inline-block;background:var(--card);border:1px solid var(--line);
    border-radius:999px;padding:4px 11px;margin:0 6px 6px 0;font-size:12.5px}}
  main{{max-width:920px;margin:0 auto;display:grid;gap:14px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:16px 18px}}
  .top{{display:flex;gap:14px;justify-content:space-between;align-items:flex-start;
    flex-wrap:wrap}}
  .rank{{color:var(--mut);font-size:12px;font-weight:600}}
  h2{{font-size:17px;margin:2px 0 3px;letter-spacing:-.01em}}
  .sub{{margin:0;color:var(--mut);font-size:13px}}
  .right{{text-align:right;display:flex;flex-direction:column;gap:6px;align-items:flex-end}}
  .badge{{font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:6px;
    letter-spacing:.03em;white-space:nowrap}}
  .score{{font-size:22px;font-weight:700;color:var(--accent);line-height:1}}
  .why{{margin:12px 0 10px;padding-left:18px}}
  .why li{{margin:2px 0;font-size:13.5px}}
  .contact{{font-size:13.5px;padding:10px 12px;border-left:3px solid var(--accent);
    background:color-mix(in srgb, var(--accent) 7%, transparent);border-radius:0 6px 6px 0}}
  .win{{font-size:12.5px;color:var(--accent);margin:9px 0 0;font-weight:600}}
  .tech,.rev{{font-size:12px;color:var(--mut);margin:6px 0 0}}
  .mut{{color:var(--mut)}}
  a{{color:var(--accent)}}
  footer{{max-width:920px;margin:28px auto 0;color:var(--mut);font-size:12px;
    border-top:1px solid var(--line);padding-top:14px}}
</style></head><body>
<header>
  <h1>Fresh US leads &mdash; {e(meta.get('date',''))}</h1>
  <p class="meta">{meta.get('reported',0)} new leads from {meta.get('queries',0)} searches
     &middot; {meta.get('found',0)} businesses seen, {meta.get('fresh',0)} never shown before
     &middot; source: {e(meta.get('source',''))}</p>
  <div>{chips}</div>
</header>
<main>{''.join(cards) if cards else '<div class="card">No new leads cleared the score threshold this run. Widen the cities or niches in config.yaml.</div>'}</main>
<footer>
  Ranked by opportunity score &mdash; higher means an easier sell.
  Call windows are converted to your IST clock.
  {attribution}
</footer>
</body></html>"""
    path.write_text(doc, encoding="utf-8")
