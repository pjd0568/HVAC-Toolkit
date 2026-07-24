from flask import Flask

from app.config import Config


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Dev convenience: stop the browser caching static JS/CSS across edits to
    # them. Without this, "I edited weathermap.js and nothing changed" is
    # indistinguishable from a real bug -- the browser just kept serving the
    # old file. Only applies under --debug; production caching is untouched.
    if app.debug:
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    from app.blueprints.converter import bp as converter_bp
    from app.blueprints.duct import bp as duct_bp
    from app.blueprints.guides import bp as guides_bp
    from app.blueprints.help import bp as help_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.pipe import bp as pipe_bp
    from app.blueprints.projects import bp as projects_bp
    from app.blueprints.psychro import bp as psychro_bp
    from app.blueprints.weather import bp as weather_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(weather_bp, url_prefix="/weather")
    app.register_blueprint(psychro_bp, url_prefix="/psychrometrics")
    app.register_blueprint(duct_bp, url_prefix="/duct-sizing")
    app.register_blueprint(pipe_bp, url_prefix="/pipe-sizing")
    app.register_blueprint(converter_bp, url_prefix="/converter")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(guides_bp, url_prefix="/reference")
    app.register_blueprint(help_bp, url_prefix="/help")

    @app.context_processor
    def inject_brand():
        return {
            "brand_name": app.config["BRAND_NAME"],
            "brand_tag": app.config["BRAND_TAG"],
        }

    @app.context_processor
    def inject_units():
        # Every template gets `U` (the unit view) and `units` (active system code),
        # so displayed values and labels are unit-aware everywhere with no per-tool
        # wiring. See app.units.get_unit_system for where the preference comes from.
        from app.units import current_view, get_unit_system

        return {"U": current_view(), "units": get_unit_system()}

    @app.context_processor
    def inject_climate_slots():
        # The 3 memory slots render as a global banner in base.html (every
        # page, not just Weather) -- see app/climate_slots.py. Injected here
        # rather than passed explicitly per-view so every current and future
        # blueprint gets the banner for free, the same reasoning as `U` above.
        from app.climate_slots import get_slots

        return {"climate_slots": get_slots()}

    @app.context_processor
    def inject_help_anchor():
        # Lets base.html's topbar Help button jump to the help section for the
        # tool the user is currently on. `active` is set per page; the button
        # looks it up in this map (falling back to the top of Help). Kept in the
        # help blueprint so the mapping stays next to the sections it points at.
        from app.blueprints.help import ACTIVE_TO_ANCHOR

        return {"help_anchor_for": ACTIVE_TO_ANCHOR}

    @app.context_processor
    def inject_access():
        # Free / Trial / Pro entitlement + module flags for every template
        # (nav Pro chips, locked panels). See app/access.py and SPEC-access.md.
        from app.access import current_access

        return {"access": current_access()}

    @app.context_processor
    def inject_paste_url():
        # Lets any template build a "paste this slot into this field group"
        # link without knowing its own route -- used by _state_input.html's
        # "Paste from Slot" buttons (see blueprints/psychro.py's
        # _paste_slot_into()). Preserves the page's *other* existing query
        # params (e.g. a different field group's own paste_<prefix>) rather
        # than resetting them, so pasting into a second group doesn't lose
        # the first paste on the same page load.
        from urllib.parse import urlencode

        from flask import request

        def paste_url(prefix: str, index: int) -> str:
            args = request.args.to_dict(flat=True)
            args[f"paste_{prefix}"] = str(index)
            return f"{request.path}?{urlencode(args)}"

        return {"paste_url": paste_url}

    return app
