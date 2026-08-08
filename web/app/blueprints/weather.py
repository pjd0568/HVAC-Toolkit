"""Site Data — Weather & Design Conditions (coming soon).

Live Open-Meteo / ERA5 lookup is disabled pending a commercial data licence
(Open-Meteo Professional and/or ASHRAE Climatic Design Data). This blueprint
serves a Coming Soon placeholder and keeps the Memory Slot clear endpoint used
by the global slot bar. The previous client and templates remain in the tree
for when the feature is re-enabled.
"""

from __future__ import annotations

from flask import Blueprint, Response, redirect, render_template, request, url_for

from app.climate_slots import clear_slot

bp = Blueprint("weather", __name__)

# Official ASHRAE climatic design tools — short-term external substitute.
ASHRAE_WEATHER_VIEWER_URL = "https://weather.ashrae.org"
ASHRAE_STATION_FINDER_URL = "https://klimaat.github.io/StationFinder/"
ASHRAE_METEO_URL = "https://ashrae-meteo.info/v3.0/"
ASHRAE_WEATHER_CENTER_URL = (
    "https://www.ashrae.org/technical-resources/bookstore/weather-data-center"
)


@bp.route("/", methods=["GET"])
def index():
    """Coming-soon placeholder — no external weather API calls."""
    return render_template(
        "weather.html",
        active="weather",
        nav="more",
        ashrae_viewer_url=ASHRAE_WEATHER_VIEWER_URL,
        ashrae_station_finder_url=ASHRAE_STATION_FINDER_URL,
        ashrae_meteo_url=ASHRAE_METEO_URL,
        ashrae_center_url=ASHRAE_WEATHER_CENTER_URL,
    )


@bp.route("/slots/clear", methods=["POST"])
def clear_slot_route():
    form = request.form
    try:
        index = int(form["index"])
    except (KeyError, ValueError):
        return Response("Invalid slot", status=400)
    try:
        clear_slot(index)
    except ValueError as exc:
        return Response(str(exc), status=400)
    return redirect(form.get("next") or url_for("weather.index"))
