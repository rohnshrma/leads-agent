"""
Fetching a web page that a business listed, safely.

The address comes from third-party data (a map listing, a business's own site), so it is hostile input:

  * only http and https, only to PUBLIC addresses. localhost, 169.254.169.254 (cloud metadata), 10.x,
    192.168.x and every other private, loopback, link-local or reserved range is refused, after the
    name has been resolved, and again after every redirect (no redirect to a private address);
  * social networks and directories are never fetched automatically - their terms forbid it. The link is
    shown to a person instead;
  * robots.txt is honoured, and an unreadable robots.txt is treated as "do not fetch";
  * a descriptive User-Agent with a contact address, a short timeout, a size cap, no crawling.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "WebiGeeksLeadAgent/1.0 (contact: rohan@webigeeksdigital.com)"
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3

# Never fetched automatically. Suffix match on the host, so m.facebook.com and www.instagram.com are covered.
NEVER_FETCH = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "tiktok.com", "twitter.com", "x.com",
    "yelp.com", "yelp.ca", "google.com", "google.ca", "goo.gl", "g.page", "maps.app.goo.gl",
    "youtube.com", "pinterest.com", "linktr.ee", "tripadvisor.com", "tripadvisor.ca", "nextdoor.com",
    "yellowpages.ca", "yellowpages.com", "canada411.ca", "411.ca", "foursquare.com", "bbb.org",
    "ratemds.com", "healthgrades.com", "zocdoc.com", "wellca.com", "opencare.com",
)


class FetchRefused(Exception):
    """The page was deliberately not fetched. The message is safe to log (no URL)."""


def host_of(url: str) -> str:
    try:
        return (urlparse(url if "//" in url else "//" + url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def is_never_fetch(url: str) -> bool:
    h = host_of(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in NEVER_FETCH)


def _public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_reserved or a.is_unspecified or getattr(a, "is_site_local", False)
                or (a.version == 6 and a.ipv4_mapped is not None and not _public_ip(str(a.ipv4_mapped))))


_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home", ".corp", ".intranet")


def resolve_public(host: str, resolver=socket.getaddrinfo) -> list[str]:
    """All addresses for a host, raising FetchRefused unless EVERY one is public."""
    if not host:
        raise FetchRefused("no host")
    h = host.lower().strip(".")
    is_ip = True
    try:
        ipaddress.ip_address(h)
    except ValueError:
        is_ip = False
    # Names that mean "this machine or an internal network" are refused before any DNS lookup, so a
    # surprising resolver answer cannot let them through. A real business site has a dotted public name.
    if not is_ip and (h == "localhost" or "." not in h or h.endswith(_INTERNAL_SUFFIXES)):
        raise FetchRefused("host is not a public address")
    try:
        ipaddress.ip_address(host)
        addrs = [host]
    except ValueError:
        try:
            addrs = sorted({info[4][0] for info in resolver(host, None)})
        except OSError:
            raise FetchRefused("host does not resolve")
    if not addrs or not all(_public_ip(a) for a in addrs):
        raise FetchRefused("host is not a public address")
    return addrs


def check_url(url: str, resolver=socket.getaddrinfo) -> str:
    """Return the url when it is safe to fetch, else raise FetchRefused."""
    if not isinstance(url, str) or len(url) > 2000:
        raise FetchRefused("bad url")
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https"):
        raise FetchRefused("only http and https")
    if u.username or u.password:
        raise FetchRefused("credentials in url")
    if u.port not in (None, 80, 443):
        raise FetchRefused("unusual port")
    if is_never_fetch(url):
        raise FetchRefused("site is not fetched automatically")
    resolve_public(u.hostname or "", resolver)
    return url.strip()


def robots_allows(url: str, session=requests, resolver=socket.getaddrinfo) -> bool:
    """True only when robots.txt could be read and permits our agent. Any doubt means no."""
    u = urlparse(url)
    robots = f"{u.scheme}://{u.netloc}/robots.txt"
    try:
        check_url(robots, resolver)
        r = session.get(robots, headers={"User-Agent": USER_AGENT}, timeout=10, allow_redirects=False)
    except (FetchRefused, requests.RequestException):
        return False
    if r.status_code in (404, 410):
        return True                       # no robots.txt: nothing is disallowed
    if r.status_code != 200:
        return False
    rp = urllib.robotparser.RobotFileParser()
    rp.parse((r.text or "")[:200_000].splitlines())
    return rp.can_fetch(USER_AGENT, url) and rp.can_fetch("*", url)


def safe_get(url: str, *, timeout: float = 10.0, session=requests, resolver=socket.getaddrinfo,
             need_robots: bool = False) -> requests.Response:
    """GET one page. Redirects are followed by hand so each hop is checked. Raises FetchRefused."""
    current = check_url(url, resolver)
    if need_robots and not robots_allows(current, session, resolver):
        raise FetchRefused("robots.txt does not allow it")
    for _ in range(MAX_REDIRECTS + 1):
        r = session.get(current, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.8"},
                        timeout=timeout, allow_redirects=False, stream=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            current = check_url(urljoin(current, r.headers["Location"]), resolver)
            continue
        if len(r.content or b"") > MAX_BYTES:
            raise FetchRefused("page too large")
        return r
    raise FetchRefused("too many redirects")
