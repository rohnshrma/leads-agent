"""One-page website mockups for leads. See render.py."""

from .niches import NICHES, niche_key_for
from .render import render_mockup, write_gallery


def build_mockups(rows: list[dict], out_dir, owner: dict | None = None) -> list[tuple[dict, dict]]:
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
    if built:
        write_gallery([m for _, m in built], out_dir)
    return built


__all__ = ["NICHES", "niche_key_for", "render_mockup", "build_mockups", "write_gallery"]
