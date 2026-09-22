"""Loader for MassiveOES-style molecular line databases.

The bundled SQLite files (OHAX, N2CB, N2PlusBX, NHAX, NOBX) follow the schema
used by MassiveOES (Voráč 2017):

    lines(id, A, air_wavelength, vacuum_wavelength, wavenumber, branch,
          upper_state -> upper_states.id, lower_state -> lower_states.id)
    upper_states(id, E_J, E_v, J, v, component)
    lower_states(id, E_J, E_v, J, v, component)

This module joins those tables and returns a pandas DataFrame compatible with
the existing molecular-band fit code (columns wavelength_nm,
energy_upper_cm1, strength, j_upper, v_upper, v_lower, branch). The strength
column is pre-weighted by the rotational degeneracy (2J'+1) so the existing
Boltzmann-population step gives the correct emission intensity per line.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[3]
BUNDLED_DIR = Path(__file__).resolve().parent / "sqlite"

# Walk up from the backend looking for "Molecular Line Data" (the layout in
# this repo places it one level above plasma-spec-studio/). Stop at the
# filesystem root to avoid infinite loops on misconfigured systems.
_MOLECULAR_DIR_NAME = "Molecular Line Data"
_MAX_PARENT_LOOKUP = 4


@dataclass(frozen=True, slots=True)
class SpeciesEntry:
    """Registry entry describing one molecular system."""

    id: str
    label: str
    db_filename: str
    description: str
    default_window_nm: tuple[float, float]
    typical_trot_K: float
    notes: str


SPECIES_REGISTRY: dict[str, SpeciesEntry] = {
    "OH_AX": SpeciesEntry(
        id="OH_AX",
        label="OH(A-X)",
        db_filename="OHAX.db",
        description="Hydroxyl A2Sigma+ to X2Pi system",
        default_window_nm=(306.0, 312.0),
        typical_trot_K=1500.0,
        notes="Strong (0,0) head near 306.4 nm and (1,1) near 312 nm. Widely used for Trot.",
    ),
    "N2_CB": SpeciesEntry(
        id="N2_CB",
        label="N2(C-B)",
        db_filename="N2CB.db",
        description="Nitrogen Second Positive System C3Piu to B3Pig",
        default_window_nm=(334.0, 339.0),
        typical_trot_K=600.0,
        notes="(0,0) head 337.13 nm; (1,2)/(2,3) bands give Tvib lever arm.",
    ),
    "N2plus_BX": SpeciesEntry(
        id="N2plus_BX",
        label="N2+(B-X)",
        db_filename="N2PlusBX.db",
        description="Nitrogen ion First Negative System B2Sigma+u to X2Sigma+g",
        default_window_nm=(388.0, 392.0),
        typical_trot_K=600.0,
        notes="(0,0) head 391.4 nm. Often used as cross-check on N2(C-B).",
    ),
    "NH_AX": SpeciesEntry(
        id="NH_AX",
        label="NH(A-X)",
        db_filename="NHAX.db",
        description="Imidogen A3Pi to X3Sigma- system",
        default_window_nm=(335.0, 338.0),
        typical_trot_K=1500.0,
        notes="(0,0) band near 336 nm; overlaps N2(C-B). DB covers 307-439 nm.",
    ),
    "NO_BX": SpeciesEntry(
        id="NO_BX",
        label="NO(B-X)",
        db_filename="NOBX.db",
        description="Nitric oxide beta system B2Pi to X2Pi",
        default_window_nm=(357.0, 425.0),
        typical_trot_K=400.0,
        notes="DB covers 357-425 nm; useful for low-temperature NO diagnostics.",
    ),
}


_CONNECTION_LOCK = threading.Lock()
_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def molecular_db_root() -> Path | None:
    """Return the directory that holds the SQLite molecular databases, or None.

    Resolution order:

    1. ``PLASMA_SPEC_MOLECULAR_DB_DIR`` environment variable.
    2. ``<project_root>/Molecular Line Data`` (the layout in this repo).
    3. ``<backend>/app/databases/molecular/sqlite`` (for self-contained
       deployments where DBs are vendored next to the code).
    """

    env = os.environ.get("PLASMA_SPEC_MOLECULAR_DB_DIR")
    if env:
        candidate = Path(env).expanduser().resolve()
        if candidate.exists():
            return candidate
    parent = BACKEND_ROOT
    for _ in range(_MAX_PARENT_LOOKUP):
        candidate = parent / _MOLECULAR_DIR_NAME
        if candidate.exists():
            return candidate
        if parent.parent == parent:
            break
        parent = parent.parent
    if BUNDLED_DIR.exists():
        return BUNDLED_DIR
    return None


def species_db_path(species_id: str) -> Path | None:
    """Resolve the SQLite file for ``species_id`` if available."""

    entry = SPECIES_REGISTRY.get(species_id)
    if entry is None:
        return None
    root = molecular_db_root()
    if root is None:
        return None
    candidate = root / entry.db_filename
    return candidate if candidate.exists() else None


def has_species_db(species_id: str) -> bool:
    return species_db_path(species_id) is not None


def _connect(species_id: str) -> sqlite3.Connection:
    path = species_db_path(species_id)
    if path is None:
        raise FileNotFoundError(
            f"molecular database for {species_id!r} not found; set "
            "PLASMA_SPEC_MOLECULAR_DB_DIR or place the file in 'Molecular Line Data/'"
        )
    with _CONNECTION_LOCK:
        conn = _CONNECTIONS.get(species_id)
        if conn is None:
            conn = sqlite3.connect(
                f"file:{path}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            _CONNECTIONS[species_id] = conn
    return conn


def list_species() -> list[dict[str, Any]]:
    """Return registry entries augmented with availability + line count info."""

    summaries: list[dict[str, Any]] = []
    for entry in SPECIES_REGISTRY.values():
        path = species_db_path(entry.id)
        if path is None:
            summaries.append(
                {
                    "id": entry.id,
                    "label": entry.label,
                    "description": entry.description,
                    "default_window_nm": list(entry.default_window_nm),
                    "typical_trot_K": entry.typical_trot_K,
                    "notes": entry.notes,
                    "available": False,
                    "database_kind": "missing",
                    "line_count": 0,
                    "wavelength_min_nm": None,
                    "wavelength_max_nm": None,
                    "path": None,
                }
            )
            continue
        try:
            stats = species_statistics(entry.id)
        except sqlite3.Error as exc:
            summaries.append(
                {
                    "id": entry.id,
                    "label": entry.label,
                    "description": entry.description,
                    "default_window_nm": list(entry.default_window_nm),
                    "typical_trot_K": entry.typical_trot_K,
                    "notes": entry.notes,
                    "available": False,
                    "database_kind": "error",
                    "line_count": 0,
                    "wavelength_min_nm": None,
                    "wavelength_max_nm": None,
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue
        summaries.append(
            {
                "id": entry.id,
                "label": entry.label,
                "description": entry.description,
                "default_window_nm": list(entry.default_window_nm),
                "typical_trot_K": entry.typical_trot_K,
                "notes": entry.notes,
                "available": True,
                "database_kind": "validated",
                "line_count": stats["line_count"],
                "wavelength_min_nm": stats["wavelength_min_nm"],
                "wavelength_max_nm": stats["wavelength_max_nm"],
                "path": str(path),
            }
        )
    return summaries


@lru_cache(maxsize=16)
def species_statistics(species_id: str) -> dict[str, Any]:
    conn = _connect(species_id)
    row = conn.execute(
        "SELECT COUNT(*) AS n, MIN(air_wavelength) AS lo, MAX(air_wavelength) AS hi FROM lines"
    ).fetchone()
    return {
        "line_count": int(row["n"]),
        "wavelength_min_nm": float(row["lo"]) if row["lo"] is not None else None,
        "wavelength_max_nm": float(row["hi"]) if row["hi"] is not None else None,
    }


def load_species_transitions(
    species_id: str,
    window_nm: tuple[float, float] | list[float] | None = None,
    jmax: float | None = None,
    branches: list[str] | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of transitions ready for the molecular fit.

    The returned columns are:

    - ``wavelength_nm``: air wavelength in nm
    - ``einstein_A``: Einstein A_ki coefficient in s^-1
    - ``upper_state_id``: database identifier for the radiating upper state
    - ``j_upper``, ``v_upper``, ``v_lower``: quantum numbers
    - ``upper_component``: component label when present in the database
    - ``e_rot_upper_cm1``, ``e_vib_upper_cm1``: rotational + vibrational
      upper-state energies in cm^-1 (separated so Phase 2 can fit Trot/Tvib)
    - ``energy_upper_cm1``: ``E_rot + E_vib`` for the existing single-T fit
    - ``branch``: branch label as stored in the database
    - ``strength``: ``A * (2 J' + 1)`` so a downstream
      ``intensity = strength * exp(-E_upper c2 / T)`` gives correct
      branch-resolved emission intensities up to a constant.
    """

    conn = _connect(species_id)
    sql = """
        SELECT
            l.upper_state AS upper_state_id,
            l.air_wavelength AS wavelength_nm,
            l.A AS einstein_A,
            l.branch AS branch,
            u.E_J AS e_rot_upper_cm1,
            u.E_v AS e_vib_upper_cm1,
            u.J AS j_upper,
            u.v AS v_upper,
            u.component AS upper_component,
            low.v AS v_lower
        FROM lines l
        JOIN upper_states u ON l.upper_state = u.id
        JOIN lower_states low ON l.lower_state = low.id
        WHERE l.air_wavelength IS NOT NULL
          AND l.A IS NOT NULL
          AND l.air_wavelength > 0
    """
    params: list[Any] = []
    if window_nm is not None:
        sql += " AND l.air_wavelength BETWEEN ? AND ?"
        params.extend([float(window_nm[0]), float(window_nm[1])])
    if jmax is not None:
        sql += " AND u.J <= ?"
        params.append(float(jmax))
    if branches:
        placeholders = ",".join(["?"] * len(branches))
        sql += f" AND l.branch IN ({placeholders})"
        params.extend(branches)
    sql += " ORDER BY l.air_wavelength"

    frame = pd.read_sql_query(sql, conn, params=params)
    if frame.empty:
        return frame.assign(
            energy_upper_cm1=pd.Series(dtype=float),
            strength=pd.Series(dtype=float),
        )

    frame["e_rot_upper_cm1"] = pd.to_numeric(frame["e_rot_upper_cm1"], errors="coerce").fillna(0.0)
    frame["e_vib_upper_cm1"] = pd.to_numeric(frame["e_vib_upper_cm1"], errors="coerce").fillna(0.0)
    frame["j_upper"] = pd.to_numeric(frame["j_upper"], errors="coerce")
    frame["einstein_A"] = pd.to_numeric(frame["einstein_A"], errors="coerce").fillna(0.0)

    frame["energy_upper_cm1"] = frame["e_rot_upper_cm1"] + frame["e_vib_upper_cm1"]
    # Degeneracy factor (2J + 1); for half-integer J this is still correct.
    degeneracy = 2.0 * frame["j_upper"].fillna(0.0) + 1.0
    frame["strength"] = frame["einstein_A"] * degeneracy
    return frame


def reset_connection_cache() -> None:
    """Close cached SQLite connections (used by tests)."""

    with _CONNECTION_LOCK:
        for conn in _CONNECTIONS.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _CONNECTIONS.clear()
    species_statistics.cache_clear()
