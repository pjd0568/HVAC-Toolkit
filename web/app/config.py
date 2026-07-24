import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


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

    # PDF report header logo — unset until a brand asset exists; the report header
    # falls back to brand-name-as-text (see web/app/reports/builder.py).
    REPORT_LOGO_PATH = os.environ.get("REPORT_LOGO_PATH", "")

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

    # Access tier override for local click-testing Free vs Pro UI.
    # None = normal trial clock; "free" | "trial" | "pro" forces that tier.
    ACCESS_DEV_TIER = os.environ.get("ACCESS_DEV_TIER") or None
