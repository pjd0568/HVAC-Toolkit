from flask import Flask, redirect, request, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
import click

from app.config import Config
from app.extensions import db, login_manager, migrate

# Marketing and account endpoints that stay public.
_PUBLIC_ENDPOINTS = frozenset(
    {
        "main.coming_soon",
        "main.health",
        "main.psychro_teaser_calculate",
        "main.track_event",
        "main.set_units",
        "main.set_flow_unit_pref",
        "auth.login",
        "auth.login_post",
        "auth.register",
        "auth.register_post",
        "billing.subscribe",
        "billing.stripe_webhook",
        "pages.terms",
        "pages.privacy",
        "pages.contact",
        "pages.about",
        "pages.methods",
        "pages.robots_txt",
        "pages.sitemap_xml",
        "pages.bing_site_auth",
        "pages.tools_index",
        "pages.tool_landing",
        "static",
    }
)

# App shell pages that still require a signed-in user.
_LOGIN_ONLY_ENDPOINTS = frozenset(
    {
        "main.dashboard",
        "v2.dashboard",
        "v2.more",
        "v2.use_mobile",
        "v2.use_classic",
    }
)

# Calculators, guides and methodology render their own upgrade panel when gated.
_ANON_APP_PREFIXES = (
    "v2.",
    "psychro.",
    "duct.",
    "pipe.",
    "refrigeration.",
    "converter.",
    "guides.",
    "methodology.",
)


def _endpoint_is_public(endpoint: str | None) -> bool:
    if endpoint is None or endpoint == "static" or endpoint in _PUBLIC_ENDPOINTS:
        return True
    if endpoint in _LOGIN_ONLY_ENDPOINTS:
        return False
    return endpoint.startswith(_ANON_APP_PREFIXES)


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
    from app.blueprints.refrigeration import bp as refrigeration_bp
    from app.blueprints.v2 import bp as v2_bp
    from app.blueprints.weather import bp as weather_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(weather_bp, url_prefix="/weather")
    app.register_blueprint(psychro_bp, url_prefix="/psychrometrics")
    app.register_blueprint(duct_bp, url_prefix="/duct-sizing")
    app.register_blueprint(pipe_bp, url_prefix="/pipe-sizing")
    app.register_blueprint(refrigeration_bp, url_prefix="/refrigeration")
    app.register_blueprint(converter_bp, url_prefix="/converter")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(guides_bp, url_prefix="/reference")
    app.register_blueprint(help_bp, url_prefix="/help")
    app.register_blueprint(methodology_bp, url_prefix="/methodology")
    app.register_blueprint(v2_bp)

    @app.before_request
    def require_login_for_app():
        endpoint = request.endpoint
        if _endpoint_is_public(endpoint):
            return None
        if current_user.is_authenticated:
            return None
        return redirect(url_for("auth.login", next=request.full_path))

    @app.context_processor
    def inject_brand():
        from flask import url_for

        mark = app.config.get("BRAND_MARK", "images/brand/icon.png")
        lockup = app.config.get("BRAND_LOCKUP", "images/brand/lockup-tagline.png")
        hero = app.config.get("BRAND_HERO", "images/brand/home-hero.png")
        favicon = app.config.get("BRAND_FAVICON", "images/brand/favicon-32.png")
        apple = app.config.get(
            "BRAND_APPLE_TOUCH", "images/brand/apple-touch-icon.png"
        )
        v = app.config.get("BRAND_ASSET_VERSION", "1")

        def _brand_url(filename: str) -> str:
            return f"{url_for('static', filename=filename)}?v={v}"

        base = app.config.get("PUBLIC_BASE_URL", "https://hvac-calcs.app").rstrip("/")
        og_path = url_for("static", filename="images/product/mixed-air-desktop.png")

        return {
            "brand_name": app.config["BRAND_NAME"],
            "brand_public": "HVAC-CALCS",
            "brand_tag": app.config["BRAND_TAG"],
            "registration_open": app.config.get("REGISTRATION_OPEN", False),
            "brand_mark_url": _brand_url(mark),
            "brand_lockup_url": _brand_url(lockup),
            "brand_hero_url": _brand_url(hero),
            "brand_favicon_url": _brand_url(favicon),
            "brand_apple_touch_url": _brand_url(apple),
            "brand_og_image_url": f"{base}{og_path}",
            "public_base_url": base,
            "legal_entity": app.config.get("LEGAL_ENTITY", "PJD IT Systems"),
            "contact_email": app.config.get("CONTACT_EMAIL", "info@hvac-calcs.app"),
            "default_meta_description": (
                f"{app.config['BRAND_NAME']} — HVAC calculators for engineers: "
                "psychrometric, duct sizing, and pipe sizing tools. "
                "SI and imperial. 14-day free trial."
            ),
        }

    @app.context_processor
    def inject_public_tools():
        from flask import g, request, url_for

        from app.seo_tools import get_landing

        endpoint_slugs = {
            "v2.single_point": "psychrometric-calculator",
            "v2.duct": "duct-sizing-calculator",
            "v2.pipe": "chilled-water-pipe-sizing",
            "v2.refrig_pt_table": "refrigerant-pt-table",
            "v2.refrig_diagnostics": "superheat-subcooling",
            "v2.converter": "unit-converter",
        }
        landing = getattr(g, "public_landing", None)
        if landing is None:
            slug = endpoint_slugs.get(request.endpoint or "")
            landing = get_landing(slug) if slug else None

        def pro_cta(next_path: str | None = None) -> dict[str, str]:
            if current_user.is_authenticated:
                return {
                    "label": "Subscribe",
                    "href": url_for("billing.subscribe"),
                }
            if app.config.get("REGISTRATION_OPEN"):
                href = (
                    url_for("auth.register", next=next_path)
                    if next_path
                    else url_for("auth.register")
                )
                return {"label": "Try Pro free", "href": href}
            return {"label": "Explore Pro", "href": url_for("billing.subscribe")}

        return {
            "public_embed": bool(getattr(g, "public_embed", False)),
            "public_landing": landing,
            "pro_cta": pro_cta,
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

    @app.cli.command("ensure-stripe-product")
    def ensure_stripe_product_command():
        """Create the monthly Managed Payments product+price if needed.

        Prints the Price ID to set as STRIPE_PRICE_ID. Requires STRIPE_SECRET_KEY
        from https://dashboard.stripe.com/test/apikeys
        """
        from app.stripe_billing import (
            StripeNotConfiguredError,
            create_subscription_product,
            resolve_price_id,
        )

        try:
            if app.config.get("STRIPE_PRICE_ID"):
                price_id = resolve_price_id()
                print(f"Using existing STRIPE_PRICE_ID={price_id}")
                return
            created = create_subscription_product()
            print("Created Stripe product + price (Test mode).")
            print(f"  product_id={created['product_id']}")
            print(f"  price_id={created['price_id']}")
            print("Add this to your environment:")
            print(f"  STRIPE_PRICE_ID={created['price_id']}")
        except StripeNotConfiguredError as exc:
            print(f"Error: {exc}")
            raise SystemExit(1) from exc

    @app.cli.command("send-test-email")
    @click.argument("to_address")
    def send_test_email_command(to_address: str):
        """Send a one-off test message via configured SMTP (MAIL_* vars)."""
        from app.mail import mail_configured, send_email

        if not mail_configured():
            click.echo(
                "Mail not configured. Set MAIL_SERVER, MAIL_USERNAME, "
                "MAIL_PASSWORD, MAIL_DEFAULT_SENDER (see .env.example).",
                err=True,
            )
            raise SystemExit(1)
        brand = app.config.get("BRAND_NAME", "hvac-calcs.app")
        ok = send_email(
            to=to_address,
            subject=f"{brand} — test email",
            body=(
                f"This is a test message from {brand}.\n\n"
                "If you received it, SMTP for info@ is working.\n"
            ),
        )
        if not ok:
            click.echo("Send failed — check logs / app password.", err=True)
            raise SystemExit(1)
        click.echo(f"Sent test email to {to_address}")

    return app
