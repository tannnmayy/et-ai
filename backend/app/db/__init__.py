"""Lightweight SQLite persistence (dispatches, audit log, sessions)."""

from backend.app.db.sqlite_store import get_db_path, init_db

__all__ = ["get_db_path", "init_db"]
