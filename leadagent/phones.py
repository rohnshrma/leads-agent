"""
Phone numbers in one canonical form (E.164) used for storing and de-duplication: North American
(+1XXXXXXXXXX) by default, Indian (+91XXXXXXXXXX) when the run's country is India (`use_country("IN")`).

Rules (NANP): ten digits, the area code and the exchange both start with 2-9, and the exchange is not
a service code such as 911 or 411. Anything else (other countries, too short, 555-01xx test numbers,
text) normalises to "" so a bad number is never saved as if it were real.
"""

from __future__ import annotations

import re

# An extension is dropped: the switchboard number is what identifies the business.
_EXT = re.compile(r"(?:ext\.?|extension|x|#)\s*\d{1,6}\s*$", re.I)
_IN_IN_TEXT = re.compile(r"(?<![\d+])(?:\+91[\s.\-]*|0)?([6-9]\d{4})[\s.\-]?(\d{5})(?!\d)")
_COUNTRY = "US"


def use_country(country: str | None) -> None:
    """Set once per run from the config: "IN" reads bare numbers as Indian, anything else as North American."""
    global _COUNTRY
    _COUNTRY = (country or "US").upper()


def normalize_indian(raw: str | None) -> str:
    """'+91 98765 43210', '098765 43210', '020 2553 1234' -> '+91' and ten digits, or ''."""
    if not raw or not isinstance(raw, str):
        return ""
    s = _EXT.sub("", raw.strip()[:40]).strip()
    if re.search(r"[A-Za-z]", s) or (s.startswith("+") and not s.startswith("+91")):
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] == "0":      # STD codes start 1-8 (011 Delhi, 0124 Gurgaon)
        return ""
    return "+91" + digits


_NA_IN_TEXT = re.compile(r"(?<!\d)(?:\+?1[\s.\-]*)?\(?([2-9]\d{2})\)?[\s.\-]*([2-9]\d{2})[\s.\-]*(\d{4})(?!\d)")


def normalize_e164(raw: str | None) -> str:
    """'(905) 726-2688 ext 4' -> '+19057262688'. Returns '' when it is not a valid NANP number.
    In an Indian run (use_country("IN")) the Indian rules apply instead."""
    if not raw or not isinstance(raw, str):
        return ""
    if _COUNTRY == "IN":
        return normalize_indian(raw)
    s = raw.strip()
    if len(s) > 40:                      # a paragraph is not a phone number
        return ""
    s = _EXT.sub("", s).strip()
    if s.startswith("+") and not s.startswith("+1"):
        return ""                        # another country's number
    if re.search(r"[A-Za-z]", s):
        return ""                        # vanity numbers ("1-800-FLOWERS") are not reliably dialable
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    area, exchange, line = digits[:3], digits[3:6], digits[6:]
    if area[0] in "01" or exchange[0] in "01":
        return ""
    if exchange[1:] == "11" or area[1:] == "11":      # 211, 311, 411 ... 911 style service codes
        return ""
    if exchange == "555" and line.startswith("01"):   # reserved for fiction
        return ""
    return "+1" + digits


def find_phone_in_text(text: str) -> str:
    """The first valid phone number for this run's country in a block of text, or ''. Strict on purpose."""
    if _COUNTRY == "IN":
        for m in _IN_IN_TEXT.finditer(text or ""):
            p = normalize_indian("".join(m.groups()))
            if p:
                return p
        return ""
    for m in _NA_IN_TEXT.finditer(text or ""):
        p = normalize_e164("".join(m.groups()))
        if p:
            return p
    return ""


def last10(phone: str | None) -> str:
    """Comparison key: the last ten digits of whatever was typed, or '' if there are fewer."""
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""
