"""Shared pytest fixtures for web app unit tests."""

import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        REGISTRATION_OPEN=True,
        TURNSTILE_SITE_KEY="",
        TURNSTILE_SECRET_KEY="",
    )
    return application
