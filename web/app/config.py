import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Load repo-root and web/ `.env` for local dev (no-op if python-dotenv missing
# or files absent). Production (Railway) injects env vars directly.
try:
    from dotenv import load_dotenv

    _web_dir = Path(__file__).resolve().parent.parent  # web/
    _repo_root = _web_dir.parent
    load_dotenv(_repo_root / ".env")
    load_dotenv(_web_dir / ".env", override=True)
except ImportError:
    pass

# Packaged V2 mark — used when REPORT_LOGO_PATH is unset.
_DEFAULT_REPORT_LOGO = (
    Path(__file__).resolve().parent / "static" / "images" / "brand" / "logo-pdf.png"
)


def normalize_database_url(url: str | None) -> str | None:
    """Normalize host URLs for SQLAlchemy + psycopg3.

    Railway often emits ``postgres://``; SQLAlchemy wants ``postgresql://``.
    With ``psycopg`` v3 the dialect is ``postgresql+psycopg://``.
    Non-local hosts get ``sslmode=require`` when missing (Railway Postgres).
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    local = host in ("localhost", "127.0.0.1", "db")
    if not local and host:
        query = parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
            parsed = parsed._replace(query=urlencode(query, doseq=True))
            url = urlunparse(parsed)
    return url


def database_url_from_env() -> str:
    return normalize_database_url(
        os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/app")
    )  # type: ignore[return-value]


class Config:
    # Brand is a single variable — swap here (or via env) when the name lands.
    BRAND_NAME = os.environ.get("BRAND_NAME", "HVAC Toolkit")
    BRAND_TAG = os.environ.get("BRAND_TAG", "working title")

    # PDF report header logo. Empty env → packaged V2 mark; missing file → text-only
    # header (see web/app/reports/builder.py). Override with a company logo path later.
    REPORT_LOGO_PATH = os.environ.get("REPORT_LOGO_PATH") or (
        str(_DEFAULT_REPORT_LOGO) if _DEFAULT_REPORT_LOGO.is_file() else ""
    )

    # Static brand mark paths (relative to the Flask static folder). Swap files in
    # static/images/brand/ to rebrand without template edits.
    # Bump when replacing brand files so Cloudflare/browser caches refresh.
    BRAND_ASSET_VERSION = os.environ.get("BRAND_ASSET_VERSION", "20260725b")

    BRAND_MARK = os.environ.get("BRAND_MARK", "images/brand/icon.svg")
    BRAND_LOCKUP = os.environ.get("BRAND_LOCKUP", "images/brand/lockup-tagline.svg")
    BRAND_FAVICON = os.environ.get("BRAND_FAVICON", "images/brand/favicon-32.png")
    BRAND_APPLE_TOUCH = os.environ.get(
        "BRAND_APPLE_TOUCH", "images/brand/apple-touch-icon.png"
    )

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # Resolved again in create_app so Railway-injected DATABASE_URL is never stale.
    SQLALCHEMY_DATABASE_URI = database_url_from_env()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Public self-serve signup. Default off so a live coming-soon site stays private.
    # Set REGISTRATION_OPEN=true when you are ready for public trials.
    REGISTRATION_OPEN = os.environ.get("REGISTRATION_OPEN", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    # Access tier override for local click-testing trial vs subscribed UI.
    # None = normal trial clock; "free" | "trial" | "pro" forces that tier
    # ("free" = trial ended / no suite access; "pro" = subscribed).
    ACCESS_DEV_TIER = os.environ.get("ACCESS_DEV_TIER") or None

    # Public site URL (canonical links, sitemap, Open Graph).
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://hvac-calcs.app").rstrip(
        "/"
    )

    # Legal / contact (marketing pages + contact form routing).
    LEGAL_ENTITY = os.environ.get("LEGAL_ENTITY", "PJD IT Systems")
    LEGAL_JURISDICTION = os.environ.get(
        "LEGAL_JURISDICTION", "England and Wales"
    )
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "info@hvac-calcs.app")

    # Preferred on Railway: Resend HTTP API (Gmail SMTP is often blocked from cloud IPs).
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

    # Optional SMTP fallback (Workspace App Password). Prefer Resend in production.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587") or "587")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "") or CONTACT_EMAIL

    # Stripe (Test mode keys from https://dashboard.stripe.com/test/apikeys).
    # Leave empty until wired; pricing page shows a disabled CTA when unset.
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    # Price ID for the £9.50/month full-suite plan (price_…). Optional if you
    # run `flask ensure-stripe-product` once to create product + price.
    STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
    # When true (default), Checkout Sessions use Managed Payments (Stripe MoR + tax).
    STRIPE_MANAGED_PAYMENTS = os.environ.get(
        "STRIPE_MANAGED_PAYMENTS", "true"
    ).lower() in ("1", "true", "yes", "on")
