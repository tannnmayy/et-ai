from __future__ import annotations

from fastapi import FastAPI

from backend.app.config import SERVICE_NAME
from backend.app.routers import copilot, forecasts, geospatial, guidance, health, intelligence, maps, neighbourhoods, travel, weather


app = FastAPI(
    title="AQI Sentinel API",
    description="Local demo API for Bengaluru PM2.5 24-hour forecasts.",
    version="0.2.0",
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


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": SERVICE_NAME, "status": "ok"}
