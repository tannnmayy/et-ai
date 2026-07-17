"""Persistence API — dispatches, audit events, optional sessions.

All endpoints are best-effort: failures return empty/error payloads with
HTTP 200 where safe so the SPA can fall back to localStorage without
hard failures. Write endpoints return 503 only when the write itself fails
after validation (so the client knows to keep local-only copy).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.db import sqlite_store as store

router = APIRouter(prefix="/persistence", tags=["persistence"])


# ---------------------------------------------------------------------------
# Schemas (camelCase to match frontend DispatchRecord)
# ---------------------------------------------------------------------------


class DispatchIn(BaseModel):
    id: str | None = None
    unitId: str
    target: str
    hexId: str = ""
    source: str = ""
    score: str = ""
    action: str = ""
    notes: str = ""
    officer: str = ""
    operator: str = ""
    status: str = Field(default="open", description="open | in_progress | resolved")
    issuedAt: str | None = None
    signedOperator: bool = False
    signedLead: bool = False


class DispatchStatusIn(BaseModel):
    status: str


class AuditEventIn(BaseModel):
    actionType: str
    context: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = None


class SessionIn(BaseModel):
    sessionKey: str = "local"
    name: str
    phone: str = ""
    email: str | None = None
    role: str = "guest"
    language: str = "en"
    acceptedTerms: bool = True
    enteredAt: str | None = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", summary="SQLite persistence health")
def persistence_health() -> dict[str, Any]:
    return store.db_health()


# ---------------------------------------------------------------------------
# Dispatches
# ---------------------------------------------------------------------------


@router.get("/dispatches", summary="List recent dispatches (newest first)")
def get_dispatches(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    items = store.list_dispatches(limit=limit)
    return {
        "source": "sqlite" if items or store.ensure_db() else "unavailable",
        "count": len(items),
        "dispatches": items,
    }


@router.get("/dispatches/{dispatch_id}", summary="Get one dispatch")
def get_one_dispatch(dispatch_id: str) -> dict[str, Any]:
    item = store.get_dispatch(dispatch_id)
    if not item:
        return {"found": False, "dispatch": None}
    return {"found": True, "dispatch": item}


@router.post("/dispatches", summary="Create or update a dispatch")
def post_dispatch(body: DispatchIn) -> dict[str, Any]:
    saved = store.upsert_dispatch(body.model_dump())
    if not saved:
        return {"ok": False, "dispatch": None, "error": "sqlite_write_failed"}
    # Best-effort audit
    store.log_audit_event(
        "dispatch_submitted",
        {
            "dispatchId": saved.get("id"),
            "unitId": saved.get("unitId"),
            "target": saved.get("target"),
            "status": saved.get("status"),
        },
        actor=saved.get("operator") or saved.get("officer"),
    )
    return {"ok": True, "dispatch": saved}


@router.patch("/dispatches/{dispatch_id}/status", summary="Update dispatch status")
def patch_dispatch_status(dispatch_id: str, body: DispatchStatusIn) -> dict[str, Any]:
    saved = store.update_dispatch_status(dispatch_id, body.status)
    if not saved:
        return {"ok": False, "dispatch": None, "error": "update_failed"}
    store.log_audit_event(
        "dispatch_status_updated",
        {"dispatchId": dispatch_id, "status": body.status},
    )
    return {"ok": True, "dispatch": saved}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@router.post("/audit", summary="Log a lightweight audit event")
def post_audit(body: AuditEventIn) -> dict[str, Any]:
    ok = store.log_audit_event(body.actionType, body.context, body.actor)
    return {"ok": ok}


@router.get("/audit", summary="List recent audit events")
def get_audit(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    events = store.list_audit_events(limit=limit)
    return {"count": len(events), "events": events}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post("/session", summary="Mirror user session to SQLite")
def post_session(body: SessionIn) -> dict[str, Any]:
    saved = store.upsert_session(body.model_dump())
    return {"ok": saved is not None, "session": saved}


@router.get("/session", summary="Get mirrored session")
def get_session(session_key: str = Query(default="local")) -> dict[str, Any]:
    sess = store.get_session(session_key)
    return {"found": sess is not None, "session": sess}
