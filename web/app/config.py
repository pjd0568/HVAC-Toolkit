import os


def normalize_database_url(url: str | None) -> str | None:
    """Normalize host URLs for SQLAlchemy + psycopg3.

    Railway often emits ``postgres://``; SQLAlchemy wants ``postgresql://``.
    With ``psycopg`` v3 the dialect is ``postgresql+psycopg://``.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Config:
    # Brand is a single variable — swap here (or via env) when the name lands.
    BRAND_NAME = os.environ.get("BRAND_NAME", "HVAC Toolkit")
    BRAND_TAG = os.environ.get("BRAND_TAG", "working title")

    # PDF report header logo — unset until a brand asset exists; the report header
    # falls back to brand-name-as-text (see web/app/reports/builder.py).
    REPORT_LOGO_PATH = os.environ.get("REPORT_LOGO_PATH", "")

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/app")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Access tier override for local click-testing Free vs Pro UI.
    # None = normal trial clock; "free" | "trial" | "pro" forces that tier.
    ACCESS_DEV_TIER = os.environ.get("ACCESS_DEV_TIER") or None
