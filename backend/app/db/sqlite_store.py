"""SQLite persistence for AQI Sentinel operational data.

Additive and non-breaking: all public functions catch errors and return
safe fallbacks so the rest of the API keeps working if the DB is missing
or locked.

Schema:
  - dispatches   — field unit dispatch orders
  - audit_events — lightweight action log
  - user_sessions — optional session mirror (name/role/language)

DB file: data/aqi_sentinel.db (under project root).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

from backend.app.config import get_project_root

logger = logging.getLogger(__name__)

_DB_REL = Path("data") / "aqi_sentinel.db"
_lock = threading.Lock()
_initialized = False


def get_db_path() -> Path:
    return get_project_root() / _DB_REL


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> bool:
    """Create tables if needed. Returns True on success."""
    global _initialized
    try:
        with _lock, _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dispatches (
                    id TEXT PRIMARY KEY,
                    unit_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    hex_id TEXT,
                    source TEXT,
                    score TEXT,
                    action TEXT,
                    notes TEXT,
                    officer TEXT,
                    operator TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    issued_at TEXT NOT NULL,
                    signed_operator INTEGER NOT NULL DEFAULT 0,
                    signed_lead INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_dispatches_issued
                    ON dispatches(issued_at DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    context_json TEXT,
                    actor TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_created
                    ON audit_events(created_at DESC);

                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_key TEXT PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    role TEXT,
                    language TEXT,
                    accepted_terms INTEGER NOT NULL DEFAULT 0,
                    entered_at TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
        _initialized = True
        logger.info("SQLite ready at %s", get_db_path())
        return True
    except Exception as exc:
        logger.warning("SQLite init failed (non-fatal): %s", exc)
        _initialized = False
        return False


def ensure_db() -> bool:
    if _initialized:
        return True
    return init_db()


# ---------------------------------------------------------------------------
# Dispatches
# ---------------------------------------------------------------------------


def _row_to_dispatch(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "unitId": row["unit_id"],
        "target": row["target"],
        "hexId": row["hex_id"] or "",
        "source": row["source"] or "",
        "score": row["score"] or "",
        "action": row["action"] or "",
        "notes": row["notes"] or "",
        "officer": row["officer"] or "",
        "operator": row["operator"] or "",
        "status": row["status"] or "open",
        "issuedAt": row["issued_at"],
        "signedOperator": bool(row["signed_operator"]),
        "signedLead": bool(row["signed_lead"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def upsert_dispatch(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Insert or update a dispatch. Returns stored record or None on failure."""
    if not ensure_db():
        return None
    try:
        now = _utcnow()
        disp_id = str(payload.get("id") or f"dsp-{int(datetime.now().timestamp() * 1000)}")
        unit_id = str(payload.get("unitId") or payload.get("unit_id") or "")
        target = str(payload.get("target") or "").strip()
        if not unit_id or not target:
            logger.warning("upsert_dispatch: missing unitId or target")
            return None

        status = str(payload.get("status") or "open").lower()
        if status not in ("open", "in_progress", "resolved"):
            status = "open"

        issued = str(payload.get("issuedAt") or payload.get("issued_at") or now)
        signed_op = 1 if payload.get("signedOperator", payload.get("signed_operator")) else 0
        signed_lead = 1 if payload.get("signedLead", payload.get("signed_lead")) else 0

        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO dispatches (
                    id, unit_id, target, hex_id, source, score, action, notes,
                    officer, operator, status, issued_at, signed_operator, signed_lead,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    unit_id=excluded.unit_id,
                    target=excluded.target,
                    hex_id=excluded.hex_id,
                    source=excluded.source,
                    score=excluded.score,
                    action=excluded.action,
                    notes=excluded.notes,
                    officer=excluded.officer,
                    operator=excluded.operator,
                    status=excluded.status,
                    issued_at=excluded.issued_at,
                    signed_operator=excluded.signed_operator,
                    signed_lead=excluded.signed_lead,
                    updated_at=excluded.updated_at
                """,
                (
                    disp_id,
                    unit_id,
                    target,
                    str(payload.get("hexId") or payload.get("hex_id") or ""),
                    str(payload.get("source") or ""),
                    str(payload.get("score") or ""),
                    str(payload.get("action") or ""),
                    str(payload.get("notes") or ""),
                    str(payload.get("officer") or ""),
                    str(payload.get("operator") or ""),
                    status,
                    issued,
                    signed_op,
                    signed_lead,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM dispatches WHERE id = ?", (disp_id,)
            ).fetchone()
        return _row_to_dispatch(row) if row else None
    except Exception as exc:
        logger.warning("upsert_dispatch failed: %s", exc)
        return None


def list_dispatches(limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first dispatch list. Empty list on failure."""
    if not ensure_db():
        return []
    try:
        limit = max(1, min(200, int(limit)))
        with _lock, _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dispatches ORDER BY issued_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dispatch(r) for r in rows]
    except Exception as exc:
        logger.warning("list_dispatches failed: %s", exc)
        return []


def get_dispatch(dispatch_id: str) -> dict[str, Any] | None:
    if not ensure_db():
        return None
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)
            ).fetchone()
        return _row_to_dispatch(row) if row else None
    except Exception as exc:
        logger.warning("get_dispatch failed: %s", exc)
        return None


def update_dispatch_status(dispatch_id: str, status: str) -> dict[str, Any] | None:
    if status not in ("open", "in_progress", "resolved"):
        return None
    if not ensure_db():
        return None
    try:
        now = _utcnow()
        with _lock, _connect() as conn:
            conn.execute(
                "UPDATE dispatches SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, dispatch_id),
            )
            row = conn.execute(
                "SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)
            ).fetchone()
        return _row_to_dispatch(row) if row else None
    except Exception as exc:
        logger.warning("update_dispatch_status failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def log_audit_event(
    action_type: str,
    context: dict[str, Any] | None = None,
    actor: str | None = None,
) -> bool:
    """Append a lightweight audit event. Never raises to callers."""
    if not action_type or not ensure_db():
        return False
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (action_type, context_json, actor, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(action_type)[:128],
                    json.dumps(context or {}, default=str)[:4000],
                    (actor or "")[:128] or None,
                    _utcnow(),
                ),
            )
        return True
    except Exception as exc:
        logger.warning("log_audit_event failed: %s", exc)
        return False


def list_audit_events(limit: int = 50) -> list[dict[str, Any]]:
    if not ensure_db():
        return []
    try:
        limit = max(1, min(200, int(limit)))
        with _lock, _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, action_type, context_json, actor, created_at
                FROM audit_events ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            ctx: Any = {}
            try:
                ctx = json.loads(r["context_json"] or "{}")
            except json.JSONDecodeError:
                ctx = {}
            out.append(
                {
                    "id": r["id"],
                    "actionType": r["action_type"],
                    "context": ctx,
                    "actor": r["actor"],
                    "createdAt": r["created_at"],
                }
            )
        return out
    except Exception as exc:
        logger.warning("list_audit_events failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# User sessions (optional mirror)
# ---------------------------------------------------------------------------


def upsert_session(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Mirror frontend session under a stable session_key (default: 'local')."""
    if not ensure_db():
        return None
    try:
        key = str(payload.get("sessionKey") or payload.get("session_key") or "local")
        now = _utcnow()
        with _lock, _connect() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (
                    session_key, name, phone, email, role, language,
                    accepted_terms, entered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    name=excluded.name,
                    phone=excluded.phone,
                    email=excluded.email,
                    role=excluded.role,
                    language=excluded.language,
                    accepted_terms=excluded.accepted_terms,
                    entered_at=excluded.entered_at,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    str(payload.get("name") or ""),
                    str(payload.get("phone") or ""),
                    str(payload.get("email") or "") or None,
                    str(payload.get("role") or "guest"),
                    str(payload.get("language") or "EN"),
                    1 if payload.get("acceptedTerms", payload.get("accepted_terms")) else 0,
                    str(payload.get("enteredAt") or payload.get("entered_at") or now),
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM user_sessions WHERE session_key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        return {
            "sessionKey": row["session_key"],
            "name": row["name"],
            "phone": row["phone"],
            "email": row["email"],
            "role": row["role"],
            "language": row["language"],
            "acceptedTerms": bool(row["accepted_terms"]),
            "enteredAt": row["entered_at"],
            "updatedAt": row["updated_at"],
        }
    except Exception as exc:
        logger.warning("upsert_session failed: %s", exc)
        return None


def get_session(session_key: str = "local") -> dict[str, Any] | None:
    if not ensure_db():
        return None
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_sessions WHERE session_key = ?",
                (session_key,),
            ).fetchone()
        if not row:
            return None
        return {
            "sessionKey": row["session_key"],
            "name": row["name"],
            "phone": row["phone"],
            "email": row["email"],
            "role": row["role"],
            "language": row["language"],
            "acceptedTerms": bool(row["accepted_terms"]),
            "enteredAt": row["entered_at"],
            "updatedAt": row["updated_at"],
        }
    except Exception as exc:
        logger.warning("get_session failed: %s", exc)
        return None


def db_health() -> dict[str, Any]:
    """Diagnostics for health checks — never throws."""
    path = get_db_path()
    try:
        ok = ensure_db()
        counts: dict[str, int] = {}
        if ok:
            with _lock, _connect() as conn:
                for table in ("dispatches", "audit_events", "user_sessions"):
                    counts[table] = int(
                        conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                    )
        return {
            "ok": ok,
            "path": str(path),
            "exists": path.exists(),
            "counts": counts,
        }
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}
