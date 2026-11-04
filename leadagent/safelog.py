"""
Run logs are public: leads-agent is a public repository, so anyone can open a finished workflow run.

The log may therefore say COUNTS ("Overpass: 120 found, 2 failed") and never a business name, phone
number, email, address, web address, place id, area, token or key. Two layers:

  1. the code prints counts only;
  2. `install()` wraps stdout and stderr so that, if a person or a library prints one by accident, it is
     masked before it is written.
"""

from __future__ import annotations

import re
import sys

_RULES = [
    (re.compile(r"https?://[^\s'\")>\]]+", re.I), "[url]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[email]"),
    (re.compile(r"(?<![\w.])(?:\+?1[\s.\-]*)?\(?[2-9]\d{2}\)?[\s.\-]*[2-9]\d{2}[\s.\-]*\d{4}(?!\d)"), "[phone]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "[key]"),
    (re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[0-9A-Za-z_]{20,}"), "[key]"),
    (re.compile(r"\bChIJ[0-9A-Za-z_\-]{10,}"), "[place-id]"),           # Google place ids
    (re.compile(r"\b(?:node|way|relation)/\d{3,}\b"), "[osm-id]"),      # OpenStreetMap ids
    (re.compile(r"(?i)\b(authorization[:=]\s*(?:bearer\s+)?|bearer\s+|x-goog-api-key[:=]\s*)\S+"), r"\1[hidden]"),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "[token]"),
]


def mask(text: str) -> str:
    for rx, repl in _RULES:
        text = rx.sub(repl, text)
    return text


class _Masking:
    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        return self._inner.write(mask(s) if isinstance(s, str) else s)

    def flush(self):
        return self._inner.flush()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install() -> None:
    """Mask everything this process prints from now on. Safe to call more than once."""
    for name in ("stdout", "stderr"):
        cur = getattr(sys, name)
        if not isinstance(cur, _Masking):
            setattr(sys, name, _Masking(cur))
