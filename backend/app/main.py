from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import SERVICE_NAME
from backend.app.routers import attribution, citizen, copilot, enforcement, forecasts, geospatial, guidance, health, intelligence, maps, neighbourhoods, stations, travel, weather


app = FastAPI(
    title="AQI Sentinel API",
    description="Local demo API for Bengaluru PM2.5 24-hour forecasts.",
    version="0.2.0",
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
app.include_router(stations.router)
app.include_router(citizen.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": SERVICE_NAME, "status": "ok"}
