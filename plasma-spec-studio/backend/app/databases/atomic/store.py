"""Searchable atomic line catalog.

Loads ``nist_lines.csv`` (the bundled NIST-derived subset) plus an optional
``user_overrides.csv`` so a user can add their own lines or NIST refreshes
without touching the bundled file. Both files share the same schema.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DATABASE_ROOT = Path(__file__).resolve().parent
BUNDLED_CSV = DATABASE_ROOT / "nist_lines.csv"
NIST_LIVE_CSV = DATABASE_ROOT / "nist_live_lines.csv"
USER_OVERRIDE_CSV = DATABASE_ROOT / "user_overrides.csv"
DEMO_CSV = DATABASE_ROOT / "demo_atomic_lines.csv"
SOURCES_JSON = DATABASE_ROOT / "sources.json"
SOURCE_PRIORITY = {"user": 0, "bundled": 1, "nist_live": 2, "demo": 3}

REQUIRED_COLUMNS = ("species", "wavelength_air_nm")
NUMERIC_COLUMNS = (
    "wavelength_air_nm",
    "A_ki_s_1",
    "E_i_cm1",
    "E_k_cm1",
    "g_i",
    "g_k",
    "wavenumber_cm1",
    "relative_intensity",
)

PREFERRED_COLUMNS = [
    "species",
    "wavelength_air_nm",
    "A_ki_s_1",
    "acc_A",
    "E_i_cm1",
    "E_k_cm1",
    "g_i",
    "g_k",
    "lower_term",
    "upper_term",
    "transition",
    "source",
    "notes",
    "nist_wavelength_source",
    "wavenumber_cm1",
    "relative_intensity",
    "transition_type",
    "tp_ref",
    "line_ref",
]


@lru_cache(maxsize=1)
def load_catalog() -> pd.DataFrame:
    """Load and merge the bundled catalog with any user override file."""

    frames: list[pd.DataFrame] = []
    if BUNDLED_CSV.exists():
        frames.append(_read_lines_csv(BUNDLED_CSV, source_tag="bundled"))
    if NIST_LIVE_CSV.exists():
        frames.append(_read_lines_csv(NIST_LIVE_CSV, source_tag="nist_live"))
    if USER_OVERRIDE_CSV.exists():
        frames.append(_read_lines_csv(USER_OVERRIDE_CSV, source_tag="user"))
    if not frames and DEMO_CSV.exists():
        # Fall back to the legacy 12-row demo only if nothing else is present.
        legacy = pd.read_csv(DEMO_CSV)
        legacy = legacy.rename(columns={"wavelength_nm": "wavelength_air_nm"})
        legacy["source_tag"] = "demo"
        frames.append(legacy)
    if not frames:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS) + ["source_tag"])

    catalog = pd.concat(frames, ignore_index=True)
    catalog = catalog.dropna(subset=["wavelength_air_nm"])
    catalog["wavelength_air_nm"] = catalog["wavelength_air_nm"].astype(float)
    catalog["species"] = catalog["species"].astype(str).str.strip()
    catalog["boltzmann_ready"] = catalog[["A_ki_s_1", "E_k_cm1", "g_k"]].notna().all(axis=1)
    return catalog.sort_values("wavelength_air_nm").reset_index(drop=True)


def _read_lines_csv(path: Path, source_tag: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(
            f"atomic line CSV {path.name} is missing required columns: {sorted(missing)}"
        )
    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source_tag"] = source_tag
    return frame


def search_lines(
    species: list[str] | str | None = None,
    wavelength_min_nm: float | None = None,
    wavelength_max_nm: float | None = None,
    energy_upper_max_cm1: float | None = None,
    require_einstein: bool = False,
    near_nm: float | None = None,
    tolerance_nm: float = 0.5,
    max_results: int = 200,
) -> list[dict[str, Any]]:
    """Search the catalog with composable filters.

    All arguments are optional. ``near_nm`` + ``tolerance_nm`` is convenient
    for "what lines are within X nm of this cursor wavelength" queries.
    """

    frame = load_catalog()
    if frame.empty:
        return []

    if species is not None:
        if isinstance(species, str):
            species = [species]
        normalized = {item.strip().lower() for item in species if item}
        frame = frame[frame["species"].str.lower().isin(normalized)]

    if wavelength_min_nm is not None:
        frame = frame[frame["wavelength_air_nm"] >= float(wavelength_min_nm)]
    if wavelength_max_nm is not None:
        frame = frame[frame["wavelength_air_nm"] <= float(wavelength_max_nm)]

    if near_nm is not None:
        delta = np.abs(frame["wavelength_air_nm"] - float(near_nm))
        keep_mask = delta <= float(tolerance_nm)
        frame = frame.loc[keep_mask].copy()
        # IMPORTANT: assign delta_nm using the filtered-index slice, not the
        # full delta series. Otherwise ``.assign`` re-broadcasts delta's full
        # index onto the empty/filtered frame and resurrects all-NaN rows.
        frame["delta_nm"] = delta.loc[keep_mask]

    if energy_upper_max_cm1 is not None and "E_k_cm1" in frame.columns:
        frame = frame[frame["E_k_cm1"] <= float(energy_upper_max_cm1)]

    if require_einstein and "A_ki_s_1" in frame.columns:
        frame = frame[frame["A_ki_s_1"].notna()]

    frame = frame.assign(_source_priority=_source_priority(frame))
    if "delta_nm" in frame.columns:
        frame = frame.sort_values(
            ["delta_nm", "_source_priority", "wavelength_air_nm", "species"],
            kind="mergesort",
        )
    else:
        frame = frame.sort_values(
            ["wavelength_air_nm", "_source_priority", "species"],
            kind="mergesort",
        )

    frame = frame.head(int(max_results))
    frame = frame.drop(columns=["_source_priority"], errors="ignore")
    return frame.replace({np.nan: None}).to_dict(orient="records")


def list_species() -> list[dict[str, Any]]:
    """Return distinct species with line counts."""

    frame = load_catalog()
    if frame.empty:
        return []
    counts = frame.groupby("species").size().reset_index(name="line_count")
    return counts.sort_values("species").to_dict(orient="records")


def catalog_summary() -> dict[str, Any]:
    """Return high-level catalog metadata for the UI."""

    frame = load_catalog()
    sources: dict[str, Any] = {}
    if SOURCES_JSON.exists():
        try:
            sources = json.loads(SOURCES_JSON.read_text())
        except json.JSONDecodeError:
            sources = {}
    source_counts = (
        frame.groupby("source_tag").size().astype(int).to_dict()
        if not frame.empty and "source_tag" in frame.columns
        else {}
    )
    return {
        "line_count": int(len(frame)),
        "species_count": int(frame["species"].nunique()) if not frame.empty else 0,
        "wavelength_min_nm": float(frame["wavelength_air_nm"].min()) if not frame.empty else None,
        "wavelength_max_nm": float(frame["wavelength_air_nm"].max()) if not frame.empty else None,
        "has_nist_live_cache": NIST_LIVE_CSV.exists(),
        "has_user_overrides": USER_OVERRIDE_CSV.exists(),
        "source_counts": source_counts,
        "nist_live_path": str(NIST_LIVE_CSV),
        "sources": sources,
    }


def write_nist_live_lines(lines: pd.DataFrame, mode: str = "append") -> dict[str, Any]:
    """Persist official NIST ASD refresh rows into the live-cache CSV."""

    if mode not in {"append", "replace"}:
        raise ValueError("mode must be 'append' or 'replace'")
    if lines.empty:
        raise ValueError("no NIST lines to persist")

    missing = set(REQUIRED_COLUMNS) - set(lines.columns)
    if missing:
        raise ValueError(f"NIST lines are missing required columns: {sorted(missing)}")

    frames = []
    if mode == "append" and NIST_LIVE_CSV.exists():
        frames.append(pd.read_csv(NIST_LIVE_CSV))
    frames.append(lines.copy())
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["species", "wavelength_air_nm"])
    combined["species"] = combined["species"].astype(str).str.strip()
    combined["wavelength_air_nm"] = pd.to_numeric(
        combined["wavelength_air_nm"], errors="coerce"
    )
    combined = combined.dropna(subset=["wavelength_air_nm"])
    for column in NUMERIC_COLUMNS:
        if column in combined.columns:
            combined[column] = pd.to_numeric(combined[column], errors="coerce")

    dedupe_columns = [
        column
        for column in ("species", "wavelength_air_nm", "transition", "A_ki_s_1")
        if column in combined.columns
    ]
    if dedupe_columns:
        combined = combined.drop_duplicates(subset=dedupe_columns, keep="last")

    combined = combined.sort_values(["species", "wavelength_air_nm"]).reset_index(drop=True)
    ordered = [column for column in PREFERRED_COLUMNS if column in combined.columns]
    ordered.extend(column for column in combined.columns if column not in ordered)

    NIST_LIVE_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined[ordered].to_csv(NIST_LIVE_CSV, index=False)
    reset_cache()
    return {
        "path": str(NIST_LIVE_CSV),
        "line_count": int(len(combined)),
        "species_count": int(combined["species"].nunique()),
    }


def reset_cache() -> None:
    """Drop the cached catalog (used by tests + the optional NIST refresh)."""

    load_catalog.cache_clear()


def _source_priority(frame: pd.DataFrame) -> pd.Series:
    if "source_tag" not in frame.columns:
        return pd.Series([99] * len(frame), index=frame.index, dtype=int)
    return frame["source_tag"].map(SOURCE_PRIORITY).fillna(99).astype(int)
