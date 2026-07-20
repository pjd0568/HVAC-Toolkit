import os


class Config:
    # Brand is a single variable — swap here (or via env) when the name lands.
    BRAND_NAME = os.environ.get("BRAND_NAME", "HVAC Toolkit")
    BRAND_TAG = os.environ.get("BRAND_TAG", "working title")

    # PDF report header logo — unset until a brand asset exists; the report header
    # falls back to brand-name-as-text (see web/app/reports/builder.py).
    REPORT_LOGO_PATH = os.environ.get("REPORT_LOGO_PATH", "")

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://app:app@db:5432/app"
    )
