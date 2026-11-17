"""
North American phone numbers: one canonical form (E.164, +1XXXXXXXXXX) used for storing and de-duplication.

Rules (NANP): ten digits, the area code and the exchange both start with 2-9, and the exchange is not
a service code such as 911 or 411. Anything else (other countries, too short, 555-01xx test numbers,
text) normalises to "" so a bad number is never saved as if it were real.
"""

from __future__ import annotations

import re

# An extension is dropped: the switchboard number is what identifies the business.
_EXT = re.compile(r"(?:ext\.?|extension|x|#)\s*\d{1,6}\s*$", re.I)
_NA_IN_TEXT = re.compile(r"(?<!\d)(?:\+?1[\s.\-]*)?\(?([2-9]\d{2})\)?[\s.\-]*([2-9]\d{2})[\s.\-]*(\d{4})(?!\d)")


def normalize_e164(raw: str | None) -> str:
    """'(905) 726-2688 ext 4' -> '+19057262688'. Returns '' when it is not a valid NANP number."""
    if not raw or not isinstance(raw, str):
        return ""
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
    """The first valid North American phone number in a block of text, or ''. Strict on purpose."""
    for m in _NA_IN_TEXT.finditer(text or ""):
        p = normalize_e164("".join(m.groups()))
        if p:
            return p
    return ""


def last10(phone: str | None) -> str:
    """Comparison key: the last ten digits of whatever was typed, or '' if there are fewer."""
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""
