"""
Website auditor + opportunity scorer.

The point of this module: "has a website" is not a yes/no question.
Four buckets actually matter for selling web work:

  NO_WEBSITE    - nothing listed at all.           Best lead.
  SOCIAL_ONLY   - the "website" is a Facebook page, Linktree, Yelp,
                  business.site, a free wixsite subdomain, etc.
                  The owner thinks they have a site. They don't.
                  Almost as good a lead, and far less contested.
  BROKEN        - a URL is listed but times out / 4xx / 5xx / parked
                  / "under construction". They are paying for a domain
                  that sells nothing. Very easy conversation.
  WEAK          - a real site that is not https, not mobile-friendly,
                  slow, or visibly stale (old copyright year).

Everything is measured from the raw HTML with no paid API.
"""

from __future__ import annotations

import re
import socket
import time
from datetime import datetime
from urllib.parse import urlparse

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
JUNK_EMAIL = re.compile(
    r"(sentry|wixpress|example\.|@\d|\.png|\.jpg|\.gif|godaddy|cloudflare"
    r"|domain\.com|email@|your@|name@)", re.I
)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}(20\d{2})", re.I)
CONSTRUCTION_RE = re.compile(
    r"(under construction|coming soon|site is being (built|updated)"
    r"|website coming|launching soon|parked (free|domain)"
    r"|buy this domain|domain (is )?for sale"
    r"|future home of|default web page|it works!)", re.I
)

PLATFORMS = [
    ("Wix", r"wix\.com|_wixCssImports|wixstatic"),
    ("Squarespace", r"squarespace|static1\.squarespace"),
    ("Shopify", r"cdn\.shopify|shopify\.com"),
    ("WordPress", r"wp-content|wp-includes|wp-json"),
    ("GoDaddy Builder", r"godaddy|img1\.wsimg\.com"),
    ("Weebly", r"weebly"),
    ("Webflow", r"webflow"),
    ("Duda", r"dudaone|multiscreensite"),
    ("Joomla", r"/media/jui/|joomla"),
    ("Drupal", r"drupal-settings-json|/sites/default/files"),
]

CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/about-us", "/contact.html")


def _norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def is_social_only(url: str, social_domains: list[str]) -> bool:
    h = _host(url)
    if not h:
        return False
    return any(h == d or h.endswith("." + d) for d in social_domains)


def harvest_emails(html: str) -> list[str]:
    found = []
    for m in EMAIL_RE.findall(html or ""):
        if JUNK_EMAIL.search(m):
            continue
        m = m.strip(".,;:")
        if m.lower() not in [f.lower() for f in found]:
            found.append(m)
    return found[:4]


def audit_site(url: str, cfg: dict) -> dict:
    """Fetch a site once and report everything we can measure."""
    wcfg = cfg.get("website_audit", {}) or {}
    timeout = int(wcfg.get("timeout_seconds", 12))
    social = [d.lower() for d in wcfg.get("social_only_domains", [])]

    res = {
        "listed_url": url, "final_url": "", "http_status": None,
        "load_seconds": None, "https": False, "mobile_friendly": None,
        "platform": "", "page_kb": None, "title": "",
        "has_meta_description": None, "copyright_year": None,
        "emails_found": "", "verdict": "",
    }

    if not url:
        res["verdict"] = "NO_WEBSITE"
        return res

    if is_social_only(url, social):
        res["verdict"] = "SOCIAL_ONLY"
        res["platform"] = _host(url)
        return res

    target = _norm_url(url)
    t0 = time.time()
    try:
        r = requests.get(
            target, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        )
    except (requests.RequestException, socket.error) as e:
        res["verdict"] = "BROKEN"
        res["http_status"] = type(e).__name__
        res["load_seconds"] = round(time.time() - t0, 2)
        return res

    res["load_seconds"] = round(time.time() - t0, 2)
    res["http_status"] = r.status_code
    res["final_url"] = r.url
    res["https"] = r.url.lower().startswith("https://")

    # Redirected to a social page? Then it is social-only after all.
    if is_social_only(r.url, social):
        res["verdict"] = "SOCIAL_ONLY"
        res["platform"] = _host(r.url)
        return res

    if r.status_code >= 400:
        res["verdict"] = "BROKEN"
        return res

    html = r.text or ""
    res["page_kb"] = round(len(r.content) / 1024.0, 1)

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    res["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:160] if m else ""
    res["has_meta_description"] = bool(
        re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'][^"\']{20,}',
                  html, re.I)
    )
    res["mobile_friendly"] = bool(
        re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I)
    )
    for name, pat in PLATFORMS:
        if re.search(pat, html, re.I):
            res["platform"] = name
            break

    cy = COPYRIGHT_RE.search(html)
    if cy:
        try:
            res["copyright_year"] = int(cy.group(1))
        except ValueError:
            pass

    body_text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html,
                       flags=re.I | re.S)
    body_text = re.sub(r"<[^>]+>", " ", body_text)
    if CONSTRUCTION_RE.search(body_text[:6000]) or len(body_text.strip()) < 350:
        res["verdict"] = "UNDER_CONSTRUCTION"
        return res

    # Email harvest: homepage, then a contact/about page.
    emails = harvest_emails(html)
    if not emails:
        base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
        for path in CONTACT_PATHS:
            try:
                r2 = requests.get(base + path, timeout=timeout,
                                  headers={"User-Agent": UA})
                if r2.status_code == 200:
                    emails = harvest_emails(r2.text)
                    if emails:
                        break
            except requests.RequestException:
                continue
    res["emails_found"] = ", ".join(emails)

    weak = (
        not res["https"] or not res["mobile_friendly"]
        or (res["load_seconds"] or 0) > 4
        or (res["copyright_year"] and res["copyright_year"] <= datetime.now().year - 2)
        or not res["has_meta_description"]
    )
    res["verdict"] = "WEAK" if weak else "OK"
    return res


def score(biz, cfg: dict) -> None:
    """Attach opportunity_score, reasons and lead_type to a Business."""
    s = cfg.get("scoring", {}) or {}
    a = biz.audit or {}
    pts, why = 0, []
    verdict = a.get("verdict", "")

    if verdict == "NO_WEBSITE":
        pts += s.get("no_website_points", 55)
        why.append("No website at all")
        biz.lead_type = "NO WEBSITE"
    elif verdict == "SOCIAL_ONLY":
        pts += s.get("social_only_points", 45)
        why.append(f"No real site - only {a.get('platform') or 'a social page'}")
        biz.lead_type = "SOCIAL ONLY"
    elif verdict == "BROKEN":
        pts += s.get("dead_site_points", 40)
        why.append(f"Site listed but does not load ({a.get('http_status')})")
        biz.lead_type = "BROKEN SITE"
    elif verdict == "UNDER_CONSTRUCTION":
        pts += s.get("under_construction_points", 35)
        why.append("Site is a placeholder / under construction")
        biz.lead_type = "PLACEHOLDER"
    else:
        biz.lead_type = "WEAK SITE" if verdict == "WEAK" else "HAS GOOD SITE"
        if not a.get("https"):
            pts += s.get("no_https_points", 12)
            why.append("No HTTPS (browsers show 'Not secure')")
        if a.get("mobile_friendly") is False:
            pts += s.get("not_mobile_friendly_points", 14)
            why.append("Not mobile-friendly (no viewport tag)")
        ls = a.get("load_seconds") or 0
        if ls > 4:
            pts += s.get("slow_load_points", 8)
            why.append(f"Slow to load ({ls}s)")
        if ls > 8:
            pts += s.get("very_slow_load_points", 6)
            why.append("Very slow (>8s)")
        cy = a.get("copyright_year")
        if cy and cy <= datetime.now().year - 2:
            pts += s.get("stale_copyright_points", 8)
            why.append(f"Looks abandoned (copyright {cy})")
        if a.get("has_meta_description") is False:
            pts += s.get("no_meta_description_points", 5)
            why.append("No meta description (hurts Google clicks)")
        if not a.get("title"):
            pts += s.get("no_title_points", 5)
            why.append("No page title (hurts Google)")

    # ---- Can they actually pay you? -------------------------------
    # Google supplies review counts; the free sources do not. So the
    # credibility signal differs by source, and the scorer uses whatever
    # is actually present rather than assuming reviews exist.
    rc = biz.review_count
    if rc is not None:
        # Google path: review count is the best proxy for real revenue.
        min_rc = s.get("min_reviews_to_qualify", 5)
        matched = False
        for threshold, bonus in (s.get("reviews_bonus_tiers") or []):
            if rc >= threshold:
                pts += bonus
                why.append(f"Proven demand ({rc} Google reviews)")
                matched = True
                break
        if not matched and rc < min_rc:
            pts -= s.get("thin_reviews_penalty", 18)
            why.append(f"Caution: only {rc} reviews - may be too small to pay")
        if (biz.rating or 0) >= 4.2 and rc >= 5:
            pts += s.get("good_rating_bonus", 6)
            why.append(f"Well liked ({biz.rating}*) - just invisible online")
    else:
        # Free-source path. No reviews exist, so stand in three signals:
        #   1. A listed phone number. A business that published a phone is
        #      running properly - and it is the only channel that reaches a
        #      no-website lead anyway, so a lead without one is near useless.
        #   2. How many datasets agreed the place exists (Overture conflates
        #      Meta + Microsoft; agreement means it is real and current).
        #   3. Overture's own confidence score.
        if biz.phone:
            pts += s.get("has_phone_points", 14)
            why.append("Phone number listed - reachable today")
        else:
            pts -= s.get("no_phone_penalty", 25)
            why.append("No phone listed - hard to reach, deprioritise")
        if biz.email:
            pts += s.get("has_email_points", 6)
            why.append("Email listed in the map data")
        if (biz.source_count or 0) >= 2:
            pts += s.get("multi_source_points", 8)
            why.append(f"Confirmed by {biz.source_count} datasets - real business")
        conf = biz.confidence
        if conf is not None:
            if conf >= 0.8:
                pts += s.get("high_confidence_points", 8)
                why.append("High confidence the business is still trading")
            elif conf < 0.55:
                pts -= s.get("low_confidence_penalty", 12)
                why.append(f"Low confidence ({conf:.2f}) - may have closed")

    # Some categories simply have the budget for a $1,500 website and some
    # do not. This keeps a dental clinic above a nail salon when both have
    # no website.
    tiers = s.get("category_value_tiers") or {}
    haystack = f"{biz.category} {biz.niche_query}".lower()
    for tier_name, spec in tiers.items():
        words = [w.lower() for w in (spec.get("match") or [])]
        if any(w in haystack for w in words):
            pts += spec.get("points", 0)
            if spec.get("points", 0) > 0:
                why.append(f"{tier_name} - typically has budget for this")
            break

    if biz.business_status and biz.business_status != "OPERATIONAL":
        pts = 0
        why = [f"Skipped: {biz.business_status}"]

    biz.opportunity_score = pts
    biz.reasons = why
