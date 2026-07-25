#!/usr/bin/env python3
"""Rasterise V2 brand mark PNGs used by favicons and PDF headers.

Run from repo root (or anywhere) with the web venv:

  web/.venv/bin/python web/app/static/images/brand/render_pngs.py

Geometry matches icon.svg / app-icon.svg so SVG and PNG stay in sync.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

NAVY = (15, 23, 42, 255)
TEAL = (20, 184, 166, 255)
SKY = (96, 165, 250, 255)
GRID = (148, 163, 184, 168)
TILE_BG = (224, 242, 254, 255)


def _cubic(p0, p1, p2, p3, steps=64):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _scale_pts(pts, s: float, ox: float = 0, oy: float = 0):
    return [(ox + x * s, oy + y * s) for x, y in pts]


def draw_mark(draw: ImageDraw.ImageDraw, size: int, *, dark: bool = False):
    """Draw the 64-unit mark into a square of `size` pixels."""
    s = size / 64.0
    grid = (100, 116, 139, 230) if dark else GRID
    curve_lo = (224, 242, 254, 255) if dark else NAVY

    lines = [[(14, 14), (50, 14), (50, 50), (14, 50), (14, 14)]]
    for x in (23, 32, 41):
        lines.append([(x, 14), (x, 50)])
    for y in (23, 32, 41):
        lines.append([(14, y), (50, y)])

    sw = max(1, round(1.0 * s))
    for poly in lines:
        draw.line(_scale_pts(poly, s), fill=grid, width=sw)

    lower = _cubic((16.5, 46), (22, 42), (28, 36), (34, 28.5))
    lower += _cubic((34, 28.5), (40, 21), (45, 16.5), (48.5, 14.5))[1:]
    upper = _cubic((16.5, 40), (23, 35), (30, 27), (37, 19.5))
    upper += _cubic((37, 19.5), (42.5, 13.5), (46.5, 11), (49, 10))[1:]

    csw = max(2, round(2.25 * s))
    draw.line(_scale_pts(lower, s), fill=curve_lo, width=csw, joint="curve")
    draw.line(_scale_pts(upper, s), fill=TEAL, width=csw, joint="curve")

    # Round line caps (Pillow lines are square-ended)
    for path, color in ((lower, curve_lo), (upper, TEAL)):
        for px, py in (path[0], path[-1]):
            x, y = px * s, py * s
            r = csw / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    nodes = [(16.5, 40), (28.5, 28.5), (40.5, 16.2)]
    r = max(2.0, 2.4 * s)
    for nx, ny in nodes:
        x, y = nx * s, ny * s
        draw.ellipse((x - r, y - r, x + r, y + r), fill=TEAL)

    bx, by = 34 * s, 28.5 * s
    br = max(2.0, 2.1 * s)
    draw.ellipse((bx - br, by - br, bx + br, by + br), fill=SKY)


def _render_hires(size: int, *, dark: bool = False, bg=None, rounded: bool = False) -> Image.Image:
    """Draw at 4× then downscale for smooth curves."""
    scale = 4
    big = size * scale
    base = Image.new("RGBA", (big, big), bg if bg is not None else (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    draw_mark(draw, big, dark=dark)
    if rounded:
        radius = int(14 / 64 * big)
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=255)
        out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        out.paste(base, (0, 0), mask)
        base = out
    return base.resize((size, size), Image.Resampling.LANCZOS)


def render_transparent_icon(path: Path, size: int = 400):
    img = _render_hires(size)
    img.save(path, "PNG")
    print(f"wrote {path.name} ({size}x{size})")


def render_app_icon(path: Path, size: int, *, dark: bool = False):
    bg = NAVY if dark else TILE_BG
    img = _render_hires(size, dark=dark, bg=bg, rounded=True)
    img.save(path, "PNG")
    print(f"wrote {path.name} ({size}x{size})")


def main():
    render_transparent_icon(HERE / "logo-pdf.png", 400)
    render_app_icon(HERE / "favicon-32.png", 32)
    render_app_icon(HERE / "apple-touch-icon.png", 180)
    render_app_icon(HERE / "app-icon-512.png", 512)
    render_app_icon(HERE / "app-icon-dark-512.png", 512, dark=True)


if __name__ == "__main__":
    main()
