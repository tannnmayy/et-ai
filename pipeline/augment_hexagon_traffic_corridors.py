"""Incrementally add traffic corridor columns to hexagon_features.parquet.

Does NOT rebuild the full OSM feature stack — only major-road corridor
scoring — so it is safe and fast to re-run when roads data is already cached.

Run:
    python -m pipeline.augment_hexagon_traffic_corridors
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.app.config import HEXAGON_FEATURES_PATH, get_project_root
from pipeline.traffic_features import (
    compute_corridor_columns_for_hex_df,
    load_major_roads_from_geojson_category,
)

logger = logging.getLogger(__name__)


def augment_hexagon_traffic_corridors(
    parquet_path: Path | None = None,
) -> Path:
    root = get_project_root()
    if parquet_path is None:
        parquet_path = root / HEXAGON_FEATURES_PATH

    if not parquet_path.exists():
        raise FileNotFoundError(
            f"hexagon features not found at {parquet_path}. "
            "Run pipeline/build_hexagon_features.py first."
        )

    df = pd.read_parquet(str(parquet_path))
    logger.info("Loaded %d hexagons from %s", len(df), parquet_path)

    major_geoms, major_tree = load_major_roads_from_geojson_category()
    scored = compute_corridor_columns_for_hex_df(df, major_geoms, major_tree)

    # Drop polygon if present (should not be in parquet)
    if "polygon" in scored.columns:
        scored = scored.drop(columns=["polygon"])

    scored.to_parquet(str(parquet_path), index=False)
    logger.info(
        "Wrote corridor-augmented hexagon features (%d rows, columns=%s) to %s",
        len(scored),
        list(scored.columns),
        parquet_path,
    )
    return parquet_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = augment_hexagon_traffic_corridors()
    print(f"Augmented hexagon features -> {path}")


if __name__ == "__main__":
    main()
