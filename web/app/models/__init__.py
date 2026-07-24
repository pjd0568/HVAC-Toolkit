"""ORM models — import User here so Flask-Migrate discovers metadata."""

from app.models.user import User

__all__ = ["User"]
