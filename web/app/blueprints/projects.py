"""Projects — placeholder for the planned Pro feature.

Renders a static preview page: dummy projects, each with dummy saved calculations.
No persistence yet. When the feature is built, subscribers will name a project and
commit calculation results to it (see REVIEW-AND-PLAN.md). Kept as its own blueprint so
wiring the real feature later is a self-contained change.
"""

from flask import Blueprint, render_template

bp = Blueprint("projects", __name__)

# Placeholder data only — illustrates the layout, not stored anywhere.
_DEMO_PROJECTS = [
    {
        "name": "Leeds Office Refurb", "badge": "L", "updated": "2 h ago",
        "calcs": [
            {"title": "AHU 1 - Coil Selection", "tool": "Cooling Coil", "disc": "air",
             "result": "63.2 kW · off-coil 12.4 °C", "status": "green"},
            {"title": "AHU 1 - Supply Pressure Drop", "tool": "Duct Sizing", "disc": "duct",
             "result": "214 Pa index run", "status": "amber"},
            {"title": "Extract Riser - Main Duct", "tool": "Duct Sizing", "disc": "duct",
             "result": "11.8 m/s · 1.9 Pa/m", "status": "red"},
            {"title": "CHW Riser - Pipe Size", "tool": "Pipe Sizing", "disc": "water",
             "result": "DN80 · 1.4 m/s", "status": "green"},
        ],
    },
    {
        "name": "Riverside Hotel - M&E", "badge": "R", "updated": "Mon",
        "calcs": [
            {"title": "Kitchen MUA - Duct Sizing", "tool": "Duct Sizing", "disc": "duct",
             "result": "7.2 m/s · 0.95 Pa/m", "status": "green"},
            {"title": "Pool AHU - Dehumidification", "tool": "AHU Design", "disc": "air",
             "result": "off-coil 4.1 °C", "status": "amber"},
            {"title": "Bedroom FCU - Pipe Size", "tool": "Pipe Sizing", "disc": "water",
             "result": "DN20 · 0.9 m/s", "status": "green"},
        ],
    },
]


@bp.get("/")
def index():
    return render_template("projects.html", active="projects", projects=_DEMO_PROJECTS)
