"""In-app Help / User Guide — one page documenting every current module.

Static content, no persistence: the template carries the full guidance (headings,
inputs, steps) so the client-side search can read it from the DOM; this blueprint
only supplies the sidebar nav model and the active->anchor map used by the topbar
Help button. Same static-content pattern as blueprints/guides.py. See
specs/SPEC-help.md; written clean-room from this app's own tools and the public
standards each module's own spec already cites.
"""

from flask import Blueprint, render_template

bp = Blueprint("help", __name__)

# Sidebar model: ordered groups, each with its sections. `id` is the in-page
# anchor (must match the <section id="..."> in help.html); `title` is the label.
HELP_NAV = [
    {
        "group": "Getting Started",
        "sections": [
            {"id": "overview", "title": "How the app works"},
            {"id": "account-billing", "title": "Account, billing & cancel"},
        ],
    },
    {
        "group": "Site Data",
        "sections": [
            {"id": "weather", "title": "Weather & Design Conditions"},
        ],
    },
    {
        "group": "Psychrometrics",
        "sections": [
            {"id": "single-point", "title": "Single Point"},
            {"id": "mixed-air", "title": "Mixed Air"},
            {"id": "cooling-coil", "title": "Cooling Coil"},
            {"id": "desiccant", "title": "Desiccant Dehumidification"},
            {"id": "heat-humidify", "title": "Heating & Humidification"},
            {"id": "adiabatic-cool", "title": "Adiabatic Cooling"},
            {"id": "ahu", "title": "AHU Design"},
        ],
    },
    {
        "group": "Air Distribution",
        "sections": [
            {"id": "duct", "title": "Duct Sizing"},
        ],
    },
    {
        "group": "Hydronics",
        "sections": [
            {"id": "pipe", "title": "Pipe Sizing"},
        ],
    },
    {
        "group": "Utilities",
        "sections": [
            {"id": "converter", "title": "Unit Converter"},
        ],
    },
    {
        "group": "Reference",
        "sections": [
            {"id": "guides", "title": "Design Guides"},
            {"id": "methodology", "title": "Methodology & Limitations"},
            {"id": "projects", "title": "Projects"},
        ],
    },
]

# Maps a page's `active` value (set by each tool's route) to the help anchor the
# topbar Help button should jump to. Anything not listed falls back to the top of
# the Help page. Kept here rather than in base.html so the mapping is testable.
ACTIVE_TO_ANCHOR = {
    "dashboard": "overview",
    "weather": "weather",
    "psychro": "single-point",
    "psychro_mix": "mixed-air",
    "psychro_coil": "cooling-coil",
    "psychro_desiccant": "desiccant",
    "psychro_heat_humidify": "heat-humidify",
    "psychro_adiabatic_cool": "adiabatic-cool",
    "psychro_ahu": "ahu",
    "duct": "duct",
    "pipe": "pipe",
    "converter": "converter",
    "guides": "guides",
    "methodology": "methodology",
    "projects": "projects",
    "help": "overview",
    "subscribe": "account-billing",
}


@bp.get("/")
def index():
    return render_template("help.html", active="help", help_nav=HELP_NAV)
