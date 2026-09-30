"""
    python3 -m leadagent.mockups --sample                  # one mockup per niche, both palettes
    python3 -m leadagent.mockups --csv out/leads-DATE.csv  # a mockup for every lead in a report
    python3 -m leadagent.mockups --check                   # verify palette contrast (WCAG AA)
"""
import argparse
import csv
import sys
from pathlib import Path

from . import NICHES, build_mockups, write_gallery
from .render import render_mockup
from .samples import SAMPLES


def _lum(hexc: str) -> float:
    r, g, b = (int(hexc.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check_palettes() -> int:
    bad = 0
    for key, cfg in NICHES.items():
        for p in cfg["palettes"]:
            tests = [
                ("ink on bg", p["ink"], p["bg"], 4.5), ("ink on surface", p["ink"], p["surface"], 4.5),
                ("muted on bg", p["muted"], p["bg"], 4.5), ("muted on surface", p["muted"], p["surface"], 4.5),
                ("muted on tint", p["muted"], p["tint"], 4.5),
                ("on_primary on primary", p["on_primary"], p["primary"], 4.5),
                ("on_accent on accent", p["on_accent"], p["accent"], 4.5),
            ]
            for label, fg, bg, need in tests:
                c = contrast(fg, bg)
                if c < need:
                    bad += 1
                    print(f"FAIL {key} / {p['name']}: {label} {fg} on {bg} = {c:.2f} (need {need})")
    print("palette contrast: all pass" if not bad else f"{bad} contrast problem(s)")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="python3 -m leadagent.mockups")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--out", default="out/mockups")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check_palettes()
    out = Path(a.out)
    if a.sample:
        items = []
        for row in SAMPLES:
            for i in range(len(NICHES[__import__("leadagent.mockups", fromlist=["x"]).niche_key_for(row)]["palettes"])):
                r = render_mockup({**row, "source_id": f"{row['source_id']}-{i}"}, out, palette_index=i)
                if r:
                    items.append(r)
                    print(f"  {r['niche']:15s} {r['palette']:16s} {r['path']}")
        write_gallery(items, out)
        return 0
    if a.csv:
        with open(a.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        built = build_mockups(rows, out)
        print(f"{len(built)} mockup(s) built from {len(rows)} lead(s) -> {out}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
