"""Reference / Design Guides — short explainer articles alongside the calculators.

Static content, no persistence: an article registry (slug/title/summary/template) and
two routes, an index and a per-article page. See SPEC-design-guides.md for scope and
sources; content is written clean-room from public standards (ASHRAE HOF, CIBSE Guide B)
with the frozen prototype closed — that project has a knowledge-base article on the same
topic and none of its text, structure or diagrams carried across.
"""

from flask import Blueprint, abort, render_template

bp = Blueprint("guides", __name__)

GUIDES = [
    {
        "slug": "add-to-mobile-homescreen",
        "title": "Add to Mobile Homescreen",
        "summary": (
            "Install HVAC Toolkit like an app on iPhone, iPad, or Android — "
            "Safari Share / Chrome Install, with step visuals for each platform."
        ),
        "disc": "app",
        "read_mins": 2,
        "template": "guides/add_to_mobile_homescreen.html",
    },
    {
        "slug": "cooling-coil-design",
        "title": "Cooling Coil Design: The Psychrometric Process and Selection Basics",
        "summary": (
            "What a chilled water or DX coil is actually doing to the air, why some "
            "coils dehumidify and others don't, and the selection choices — face "
            "velocity, rows, condensate, frost limits — that follow from it."
        ),
        "disc": "air",
        "read_mins": 7,
        "template": "guides/cooling_coil_design.html",
    },
    {
        "slug": "steam-humidification",
        "title": "Thermodynamics of Steam Humidification in HVAC Systems",
        "summary": (
            "Why steam humidification is drawn as isothermal on the chart even though "
            "enthalpy rises; mass and energy balances, the small dry-bulb drift, and "
            "when to use the ideal model versus a full enthalpy-slope solution."
        ),
        "disc": "air",
        "read_mins": 8,
        "template": "guides/steam_humidification.html",
    },
    {
        "slug": "pipe-sizing-design-limits",
        "title": "Pipe Sizing Design Limits: Velocity and Pressure-Gradient Bands",
        "summary": (
            "The green / amber / red traffic-light bands used by the Pipe Sizing "
            "tool — ideal ΔP/L 200–300 Pa/m, per-DN velocity limits, and what "
            "CAPEX-heavy vs CAPEX-light sizing means in practice."
        ),
        "disc": "water",
        "read_mins": 4,
        "template": "guides/pipe_sizing_design_limits.html",
    },
]


@bp.get("/")
def index():
    return render_template("guides.html", active="guides", nav="more", guides=GUIDES)


@bp.get("/<slug>")
def article(slug):
    guide = next((g for g in GUIDES if g["slug"] == slug), None)
    if guide is None:
        abort(404)
    return render_template("guide_article.html", active="guides", nav="more", guide=guide)
