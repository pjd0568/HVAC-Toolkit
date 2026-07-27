from flask import Flask, redirect, request, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensions import db, login_manager, migrate

# Paths that stay public while the calculator shell requires login.
_PUBLIC_ENDPOINTS = frozenset(
    {
        "main.coming_soon",
        "main.health",
        "auth.login",
        "auth.login_post",
        "auth.register",
        "auth.register_post",
        "billing.subscribe",
        "pages.terms",
        "pages.privacy",
        "pages.contact",
        "pages.robots_txt",
        "pages.sitemap_xml",
        "static",
    }
)


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Re-read at boot so private networking / plugin URLs are always current.
    from app.config import database_url_from_env

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url_from_env()

    # Cloudflare / Railway terminate TLS and forward the real scheme/host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Dev convenience: stop the browser caching static JS/CSS across edits to
    # them. Without this, "I edited weathermap.js and nothing changed" is
    # indistinguishable from a real bug -- the browser just kept serving the
    # old file. Only applies under --debug; production caching is untouched.
    if app.debug:
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # Ensure schema exists even if Railway's releaseCommand was skipped
    # (e.g. first deploys before DATABASE_URL was attached).
    with app.app_context():
        try:
            from flask_migrate import upgrade

            upgrade()
        except Exception:
            app.logger.exception("Database migration failed at startup")

    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.billing import bp as billing_bp
    from app.blueprints.converter import bp as converter_bp
    from app.blueprints.duct import bp as duct_bp
    from app.blueprints.guides import bp as guides_bp
    from app.blueprints.help import bp as help_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.methodology import bp as methodology_bp
    from app.blueprints.pages import bp as pages_bp
    from app.blueprints.pipe import bp as pipe_bp
    from app.blueprints.projects import bp as projects_bp
    from app.blueprints.psychro import bp as psychro_bp
    from app.blueprints.weather import bp as weather_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(weather_bp, url_prefix="/weather")
    app.register_blueprint(psychro_bp, url_prefix="/psychrometrics")
    app.register_blueprint(duct_bp, url_prefix="/duct-sizing")
    app.register_blueprint(pipe_bp, url_prefix="/pipe-sizing")
    app.register_blueprint(converter_bp, url_prefix="/converter")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(guides_bp, url_prefix="/reference")
    app.register_blueprint(help_bp, url_prefix="/help")
    app.register_blueprint(methodology_bp, url_prefix="/methodology")

    @app.before_request
    def require_login_for_app():
        endpoint = request.endpoint
        if endpoint is None or endpoint in _PUBLIC_ENDPOINTS:
            return None
        if current_user.is_authenticated:
            return None
        return redirect(url_for("auth.login", next=request.full_path))

    @app.context_processor
    def inject_brand():
        from flask import url_for

        mark = app.config.get("BRAND_MARK", "images/brand/icon.svg")
        lockup = app.config.get("BRAND_LOCKUP", "images/brand/lockup-tagline.svg")
        favicon = app.config.get("BRAND_FAVICON", "images/brand/favicon-32.png")
        apple = app.config.get(
            "BRAND_APPLE_TOUCH", "images/brand/apple-touch-icon.png"
        )
        v = app.config.get("BRAND_ASSET_VERSION", "1")

        def _brand_url(filename: str) -> str:
            return f"{url_for('static', filename=filename)}?v={v}"

        return {
            "brand_name": app.config["BRAND_NAME"],
            "brand_tag": app.config["BRAND_TAG"],
            "registration_open": app.config.get("REGISTRATION_OPEN", False),
            "brand_mark_url": _brand_url(mark),
            "brand_lockup_url": _brand_url(lockup),
            "brand_favicon_url": _brand_url(favicon),
            "brand_apple_touch_url": _brand_url(apple),
            "public_base_url": app.config.get(
                "PUBLIC_BASE_URL", "https://hvac-calcs.app"
            ),
            "legal_entity": app.config.get("LEGAL_ENTITY", "PJD IT Systems"),
            "contact_email": app.config.get("CONTACT_EMAIL", "info@hvac-calcs.app"),
            "default_meta_description": (
                f"{app.config['BRAND_NAME']} — professional HVAC calculators for "
                "engineers: psychrometrics, duct sizing, pipe sizing, and more."
            ),
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
        # Trial / subscription entitlement for every template (nav chips,
        # suite gates). See app/access.py and SPEC-access.md.
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

        from flask import request as flask_request

        def paste_url(prefix: str, index: int) -> str:
            args = flask_request.args.to_dict(flat=True)
            args[f"paste_{prefix}"] = str(index)
            return f"{flask_request.path}?{urlencode(args)}"

        return {"paste_url": paste_url}

    return app
