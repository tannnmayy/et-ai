from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import SERVICE_NAME

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
