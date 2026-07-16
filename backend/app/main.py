from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import SERVICE_NAME
from backend.app.routers import (
    attribution,
    citizen,
    copilot,
    enforcement,
    forecasts,
    geospatial,
    guidance,
    health,
    insights,
    intelligence,
    maps,
    neighbourhoods,
    persistence,
    stations,
    travel,
    weather,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Best-effort SQLite init — never block startup if DB fails
    try:
        from backend.app.db.sqlite_store import init_db

        ok = init_db()
        if ok:
            logger.info("Persistence SQLite initialized")
        else:
            logger.warning("Persistence SQLite unavailable; SPA will use localStorage")
    except Exception as exc:
        logger.warning("Persistence init error (non-fatal): %s", exc)
    yield


app = FastAPI(
    title="AQI Sentinel API",
    description="Local demo API for Bengaluru PM2.5 24-hour forecasts.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(forecasts.router)
app.include_router(intelligence.router)
app.include_router(copilot.router)
app.include_router(guidance.router)
app.include_router(weather.router)
app.include_router(travel.router)
app.include_router(geospatial.router)
app.include_router(maps.router)
app.include_router(neighbourhoods.router)
app.include_router(attribution.router)
app.include_router(enforcement.router)
app.include_router(insights.router)
app.include_router(stations.router)
app.include_router(citizen.router)
app.include_router(persistence.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": SERVICE_NAME, "status": "ok"}
