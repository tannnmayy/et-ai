from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


BENGALURU_STATIONS: list[StationConfig] = [
    StationConfig(
        station_id="cpcb_hebbal",
        station_name="Hebbal, Bengaluru - KSPCB",
        source_file="hebbal_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_hombegowda",
        station_name="Hombegowda Nagar, Bengaluru - KSPCB",
        source_file="hombegowda_nagar_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_jayanagar5",
        station_name="Jayanagar 5th Block, Bengaluru - KSPCB",
        source_file="jayanagar_5th_block_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_silkboard",
        station_name="Silk Board, Bengaluru - KSPCB",
        source_file="silk_board_bengaluru_kspcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_peenya",
        station_name="Peenya, Bengaluru - CPCB",
        source_file="peenya_bengaluru_cpcb_15m.csv",
    ),
    StationConfig(
        station_id="cpcb_bapujinagar",
        station_name="Bapuji Nagar, Bengaluru - KSPCB",
        source_file="bapuji_nagar_bengaluru_kspcb_15m.csv",
    ),
]

BENGALURU_STATION_IDS: list[str] = [s.station_id for s in BENGALURU_STATIONS]

_STATION_BY_ID: dict[str, StationConfig] = {s.station_id: s for s in BENGALURU_STATIONS}


def get_station_by_id(station_id: str) -> StationConfig:
    if station_id not in _STATION_BY_ID:
        raise KeyError(f"Unknown station_id: {station_id}. Known: {', '.join(BENGALURU_STATION_IDS)}")
    return _STATION_BY_ID[station_id]


def all_station_ids() -> list[str]:
    return list(BENGALURU_STATION_IDS)


def station_raw_path(project_root: Path, config: StationConfig) -> Path:
    return project_root / "data" / "raw" / "cpcb" / config.source_file


def station_output_dir(project_root: Path, station_id: str) -> Path:
    return project_root / "data" / "processed" / "real" / station_id


def station_id_to_cpcb_config(config: StationConfig) -> CPCBStationConfig:
    return CPCBStationConfig(
        station_id=config.station_id,
        station_name=config.station_name,
        source=config.source,
        latitude=config.latitude,
        longitude=config.longitude,
        source_timezone=config.source_timezone,
    )
