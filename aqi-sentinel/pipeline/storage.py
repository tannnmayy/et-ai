from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd


def validate_columns(frame: pd.DataFrame, required_columns: Iterable[str], label: str) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    ensure_parent(path)
    frame.to_csv(path, index=False)


def read_csv(path: Path, required_columns: Iterable[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    frame = pd.read_csv(path)
    if required_columns is not None:
        validate_columns(frame, required_columns, str(path))
    return frame


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    ensure_parent(path)
    frame.to_parquet(path, index=False)


def read_parquet(path: Path, required_columns: Iterable[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input Parquet not found: {path}")
    frame = pd.read_parquet(path)
    if required_columns is not None:
        validate_columns(frame, required_columns, str(path))
    return frame
