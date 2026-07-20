"""Static site-location map for the Weather tool's PDF report.

The live tool uses an interactive Leaflet map, which has nothing to export
directly (it's DOM/JS, not an image the server can hand to reportlab) -- so this
renders a small standalone PNG snapshot from the same OpenStreetMap tiles via
the `staticmap` package (no API key, same tile family as weathermap.js). This
is the map equivalent of reports/chart.py's psychrometric chart PNG: "render a
static image of what's already on screen" for the PDF, kept in its own module
because it has nothing to do with psychrometrics or matplotlib.

Unlike the rest of PDF generation (which is fully offline once the calculation
inputs are known), this makes a handful of small tile requests over the
network -- an acceptable trade-off here, since the Weather tool's on-screen
results already require network access to exist at all (see weather_client.py).
"""

from __future__ import annotations

import io

from staticmap import CircleMarker, StaticMap

MAP_WIDTH = 640
MAP_HEIGHT = 360
MAP_ASPECT = MAP_HEIGHT / MAP_WIDTH  # for reports.builder.build_pdf's chart_aspect
DEFAULT_ZOOM = 12

# Same tile family the live map uses (see static/js/weathermap.js).
_TILE_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"


def render_location_map_png(lat: float, lon: float, zoom: int = DEFAULT_ZOOM) -> bytes:
    """A small PNG snapshot centred on (lat, lon) with a single marker."""
    m = StaticMap(MAP_WIDTH, MAP_HEIGHT, url_template=_TILE_URL)
    m.add_marker(CircleMarker((lon, lat), "#2F6FB2", 16))
    image = m.render(zoom=zoom)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


__all__ = ["MAP_WIDTH", "MAP_HEIGHT", "MAP_ASPECT", "DEFAULT_ZOOM", "render_location_map_png"]
