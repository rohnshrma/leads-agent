"""One-page website mockups for leads. See render.py."""

from .niches import NICHES, niche_key_for
from .render import render_mockup, write_gallery


def build_mockups(rows: list[dict], out_dir, owner: dict | None = None, gallery: bool = True) -> list[tuple[dict, dict]]:
    """Render a mockup for every row that fits a niche; returns (row, result) pairs."""
    built = []
    for row in rows:
        try:
            res = render_mockup(row, out_dir, owner=owner)
        except Exception as exc:  # one bad lead must never stop the run
            print(f"  mockup failed for {row.get('name')!r}: {exc}")
            continue
        if res:
            built.append((row, res))
    if built and gallery:
        write_gallery([m for _, m in built], out_dir)
    elif built:
        # Public hosting: no list of pages, and ask crawlers to stay away.
        from pathlib import Path
        d = Path(out_dir)
        (d / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        (d / "vercel.json").write_text(
            '{"headers":[{"source":"/(.*)","headers":[{"key":"X-Robots-Tag","value":"noindex, nofollow, noarchive"}]}]}',
            encoding="utf-8")
        (d / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><meta name=robots content='noindex,nofollow'>"
            "<title>Design previews</title><p style='font:16px system-ui;padding:40px'>"
            "Private design previews.</p>", encoding="utf-8")
    return built


__all__ = ["NICHES", "niche_key_for", "render_mockup", "build_mockups", "write_gallery"]
