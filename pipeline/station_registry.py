from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.cpcb_csv_adapter import CPCBStationConfig


@dataclass(frozen=True)
class StationConfig:
    station_id: str
    station_name: str
    source_file: str
    source_timezone: str = "Asia/Kolkata"
    latitude: float | None = None
    longitude: float | None = None
    source: str = "CPCB/KSPCB 15-minute station export"
    display_name: str = ""
    city: str = "bengaluru"
    active: bool = True
    geospatial_eligible: bool = True
    raw_filename: str = ""


# ---------------------------------------------------------------------------
# Hardcoded fallback (6 stations, unchanged)
# ---------------------------------------------------------------------------

_FALLBACK_STATIONS: list[StationConfig] = [
    StationConfig(
        station_id="cpcb_hebbal",
        station_name="Hebbal, Bengaluru - KSPCB",
        source_file="hebbal_bengaluru_kspcb_15m.csv",
        display_name="Hebbal Bengaluru - KSPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="hebbal_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_hombegowda",
        station_name="Hombegowda Nagar, Bengaluru - KSPCB",
        source_file="hombegowda_nagar_bengaluru_kspcb_15m.csv",
        display_name="Hombegowda Nagar Bengaluru - KSPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="hombegowda_nagar_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_jayanagar5",
        station_name="Jayanagar 5th Block, Bengaluru - KSPCB",
        source_file="jayanagar_5th_block_bengaluru_kspcb_15m.csv",
        display_name="Jayanagar 5th Block Bengaluru - KSPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="jayanagar_5th_block_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_silkboard",
        station_name="Silk Board, Bengaluru - KSPCB",
        source_file="silk_board_bengaluru_kspcb_15m.csv",
        display_name="Silk Board Bengaluru - KSPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="silk_board_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_peenya",
        station_name="Peenya, Bengaluru - CPCB",
        source_file="peenya_bengaluru_cpcb_15m.csv",
        display_name="Peenya Bengaluru - CPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="peenya_bengaluru_cpcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_bapujinagar",
        station_name="Bapuji Nagar, Bengaluru - KSPCB",
        source_file="bapuji_nagar_bengaluru_kspcb_15m.csv",
        display_name="Bapuji Nagar Bengaluru - KSPCB",
        city="bengaluru", active=True, geospatial_eligible=True,
        raw_filename="bapuji_nagar_bengaluru_kspcb_15m.csv",
    ),
]

BENGALURU_STATIONS: list[StationConfig] = list(_FALLBACK_STATIONS)
BENGALURU_STATION_IDS: list[str] = [s.station_id for s in BENGALURU_STATIONS]

_STATION_BY_ID: dict[str, StationConfig] = {s.station_id: s for s in BENGALURU_STATIONS}

# ---------------------------------------------------------------------------
# CSV-backed registry (lazy, mtime-cached)
# ---------------------------------------------------------------------------

_REGISTRY_PATH: Path | None = None
_REGISTRY_MTIME: float = 0.0


def _get_project_root() -> Path:
    try:
        from backend.app.config import get_project_root as _root
        return _root()
    except ImportError:
        return Path(__file__).resolve().parents[1]


def _get_registry_path() -> Path:
    global _REGISTRY_PATH
    if _REGISTRY_PATH is None:
        _REGISTRY_PATH = _get_project_root() / "data" / "reference" / "bengaluru_station_registry.csv"
    return _REGISTRY_PATH


def load_registry_from_csv() -> list[dict[str, Any]]:
    import pandas as pd

    path = _get_registry_path()
    if not path.exists():
        return []
    df = pd.read_csv(path)
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        records.append({
            "station_id": str(row.get("station_id", "")).strip(),
            "display_name": str(row.get("display_name", "")).strip(),
            "city": str(row.get("city", "bengaluru")).strip().lower(),
            "latitude": _safe_float(row, "latitude"),
            "longitude": _safe_float(row, "longitude"),
            "source": str(row.get("source", "")).strip(),
            "raw_filename": str(row.get("raw_filename", "")).strip(),
            "active": _safe_bool(row, "active", True),
            "geospatial_eligible": _safe_bool(row, "geospatial_eligible", True),
        })
    return records


def _cfg_from_record(r: dict[str, Any]) -> StationConfig:
    sid = r["station_id"]
    raw = r.get("raw_filename") or ""
    display = r.get("display_name") or sid
    source_file = raw or f"{sid.replace('cpcb_', '')}.csv"
    return StationConfig(
        station_id=sid,
        station_name=display,
        source_file=source_file,
        latitude=r.get("latitude"),
        longitude=r.get("longitude"),
        source=r.get("source") or "CPCB/KSPCB",
        display_name=display,
        city=r.get("city") or "bengaluru",
        active=r.get("active", True),
        geospatial_eligible=r.get("geospatial_eligible", True),
        raw_filename=raw,
    )


def get_registry_stations() -> list[StationConfig]:
    global _REGISTRY_MTIME
    path = _get_registry_path()
    current_mtime = path.stat().st_mtime if path.exists() else 0.0
    if current_mtime > _REGISTRY_MTIME:
        refresh_registry()
    if current_mtime == 0.0 and not _STATION_BY_ID:
        return list(_FALLBACK_STATIONS)
    records = load_registry_from_csv()
    return [_cfg_from_record(r) for r in records if r.get("active", True)]


def refresh_registry() -> None:
    global BENGALURU_STATIONS, BENGALURU_STATION_IDS, _STATION_BY_ID, _REGISTRY_MTIME
    path = _get_registry_path()
    if not path.exists():
        _REGISTRY_MTIME = 0.0
        BENGALURU_STATIONS = list(_FALLBACK_STATIONS)
    else:
        _REGISTRY_MTIME = path.stat().st_mtime
        records = load_registry_from_csv()
        stations = [_cfg_from_record(r) for r in records if r.get("active", True)]
        if not stations:
            BENGALURU_STATIONS = list(_FALLBACK_STATIONS)
        else:
            BENGALURU_STATIONS = stations
    BENGALURU_STATION_IDS = [s.station_id for s in BENGALURU_STATIONS]
    _STATION_BY_ID = {s.station_id: s for s in BENGALURU_STATIONS}


def _ensure_fresh() -> None:
    path = _get_registry_path()
    if path.exists() and path.stat().st_mtime > _REGISTRY_MTIME:
        refresh_registry()


def get_station_by_id(station_id: str) -> StationConfig:
    _ensure_fresh()
    if station_id not in _STATION_BY_ID:
        raise KeyError(f"Unknown station_id: {station_id}. Known: {', '.join(BENGALURU_STATION_IDS)}")
    return _STATION_BY_ID[station_id]


def all_station_ids() -> list[str]:
    _ensure_fresh()
    return list(BENGALURU_STATION_IDS)


def station_raw_path(project_root: Path, config: StationConfig) -> Path:
    return project_root / "data" / "raw" / "cpcb" / config.source_file


def station_output_dir(project_root: Path, station_id: str) -> Path:
    return project_root / "data" / "processed" / "real" / station_id


def station_id_to_cpcb_config(config: StationConfig) -> CPCBStationConfig:
    return CPCBStationConfig(
        station_id=config.station_id,
        station_name=config.display_name or config.station_name,
        source=config.source,
        latitude=config.latitude,
        longitude=config.longitude,
        source_timezone=config.source_timezone,
    )


def get_city_stations(city: str = "bengaluru") -> list[StationConfig]:
    return [s for s in get_registry_stations() if s.city.lower() == city.lower()]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(row: Any, key: str) -> float | None:
    val = row.get(key)
    if val is None or (isinstance(val, float) and str(val) == "nan"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_bool(row: Any, key: str, default: bool = False) -> bool:
    val = row.get(key)
    if val is None or (isinstance(val, float) and str(val) == "nan"):
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)
