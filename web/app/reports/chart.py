"""Server-side psychrometric chart renderer for PDF reports.

Renders the *same* payload dict app.chart.chart_payload() produces for the
on-screen SVG chart (psychart.js) -- t_min/t_max/w_max, saturation curve,
RH curves, points, segments -- so the PDF chart can never disagree with the
on-screen one; this is a second renderer over one source of data, not a
second chart-geometry implementation. The payload is already converted into
the caller's active display system (SI or IP) and carries its own unit
symbols and per-point labels, so this module never hardcodes a unit either.

Adds, per point, a dashed red guide line to each axis (horizontal to the
moisture-content axis, vertical down to the dry-bulb axis), each labelled
with the value being read off -- the same call-outs the on-screen chart now
also draws (see psychart.js), reproduced here because a PDF reader can't
hover an SVG for a live read-off.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless -- no display server in the web container

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

# Match the app's own palette (see app/static/css/app.css :root).
_INK = "#12151A"
_MUTED = "#5A636E"
_LINE = "#C5CCD5"
_GRID = "#D5DAE0"
_POINT = "#1A4F7A"   # --blue
_PROCESS = "#00A99D"  # --green
_GUIDE = "#C94444"    # --tl-red


def render_chart(payload: dict, *, width_in: float = 7.2, height_in: float = 4.4,
                  dpi: int = 150) -> bytes:
    """Render `payload` (from app.chart.chart_payload()) to a PNG, return the bytes."""
    t_min, t_max, w_max = payload["t_min"], payload["t_max"], payload["w_max"]
    points = payload["points"]
    segments = payload["segments"]

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    ax.grid(True, color=_GRID, linewidth=0.6, zorder=0)

    # Saturation curve.
    sat = payload["sat"]
    ax.plot([p[0] for p in sat], [p[1] for p in sat], color=_INK, linewidth=1.4, zorder=3)
    ax.annotate("Saturation", (sat[-1][0], sat[-1][1]), fontsize=6.5, color=_MUTED,
                xytext=(-4, 4), textcoords="offset points", ha="right")

    # Faint constant-RH curves, labelled once near their right-hand end.
    for rh_pct, curve in sorted(payload["rh_curves"].items(), key=lambda kv: int(kv[0])):
        xs = [p[0] for p in curve]
        ys = [p[1] for p in curve]
        ax.plot(xs, ys, color=_MUTED, linewidth=0.6, alpha=0.6, zorder=1)
        for x, y in zip(reversed(xs), reversed(ys)):
            if y <= w_max:
                ax.annotate(f"{rh_pct}%", (x, y), fontsize=6, color=_MUTED,
                            xytext=(3, 0), textcoords="offset points", va="center")
                break

    # Process lines between points (drawn under the points/markers).
    for i, j in segments:
        p1, p2 = points[i], points[j]
        ax.plot([p1["t"], p2["t"]], [p1["w"], p2["w"]], color=_PROCESS,
                 linewidth=1.8, zorder=4)

    # Dashed red guide lines to both axes, one pair per point, each labelled with
    # the pre-formatted, unit-aware value from the payload (SI or IP alike).
    for pt in points:
        t, w = pt["t"], pt["w"]
        ax.plot([t_min, t], [w, w], color=_GUIDE, linewidth=0.9, linestyle="--", zorder=2)
        ax.plot([t, t], [0.0, w], color=_GUIDE, linewidth=0.9, linestyle="--", zorder=2)
        ax.annotate(pt["w_label"], (t_min, w), fontsize=6.5, color=_GUIDE,
                    xytext=(3, 2), textcoords="offset points", ha="left", va="bottom")
        ax.annotate(pt["t_label"], (t, 0.0), fontsize=6.5, color=_GUIDE,
                    xytext=(3, 3), textcoords="offset points", ha="left", va="bottom")

    # Points on top, labelled with the same tags used in the results table.
    for pt in points:
        ax.scatter([pt["t"]], [pt["w"]], color=_POINT, s=30, zorder=5,
                   edgecolors="white", linewidths=0.7)
        ax.annotate(pt["label"], (pt["t"], pt["w"]), fontsize=8, fontweight="bold",
                    color=_INK, xytext=(6, 6), textcoords="offset points", zorder=6)

    ax.set_xlim(t_min, t_max)
    ax.set_ylim(0.0, w_max)
    # Same grid step the on-screen chart uses (app.chart._nice_step), so the PDF
    # and SVG charts read off the same gridlines in either unit system. Guarded:
    # an unexpected step value (e.g. 0, or a step that would make matplotlib
    # generate an excessive number of ticks) must never take the whole chart
    # image down -- fall back to matplotlib's own automatic ticks instead.
    try:
        t_step, w_step = payload["t_step"], payload["w_step"]
        if not (t_step > 0 and w_step > 0):
            raise ValueError("non-positive tick step")
        ax.xaxis.set_major_locator(MultipleLocator(t_step))
        ax.yaxis.set_major_locator(MultipleLocator(w_step))
    except Exception:
        pass
    ax.set_xlabel(f"Dry-bulb Temperature ({payload['t_sym']})", fontsize=9, color=_INK)
    ax.set_ylabel(f"Moisture Content ({payload['w_sym']} dry air)", fontsize=9, color=_INK)
    ax.tick_params(labelsize=8, colors=_INK)
    for spine in ax.spines.values():
        spine.set_color(_LINE)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
