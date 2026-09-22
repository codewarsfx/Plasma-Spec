"""Local SQLite plus file-backed spectrum storage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from app.core.spectrum import Spectrum
from app.preprocessing.filename_metadata import extract_from_filename
from app.preprocessing.importers import (
    EXCEL_EXTENSIONS,
    load_spectrum_excel,
    load_spectrum_text,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(
    os.environ.get("PLASMA_SPEC_STORAGE_DIR", str(BACKEND_ROOT / "storage"))
).expanduser()
SPECTRA_DIR = STORAGE_ROOT / "spectra"
EXPORTS_DIR = STORAGE_ROOT / "exports"
DB_PATH = STORAGE_ROOT / "plasma_spec_studio.sqlite3"


def initialize_storage() -> None:
    """Create local storage directories and SQLite tables."""

    SPECTRA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spectra (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                array_path TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                preprocessing_history_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                diagnostic TEXT NOT NULL,
                recipe_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fit_results (
                id TEXT PRIMARY KEY,
                spectrum_id TEXT,
                diagnostic TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exports (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def save_spectrum(spectrum: Spectrum) -> Spectrum:
    """Persist a spectrum array as CSV and metadata/history in SQLite."""

    initialize_storage()
    array_path = SPECTRA_DIR / f"{spectrum.id}.csv"
    pd.DataFrame(
        {"wavelength_nm": spectrum.wavelength_nm, "intensity": spectrum.intensity}
    ).to_csv(array_path, index=False)
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO spectra
            (id, filename, array_path, metadata_json, preprocessing_history_json, created_at)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM spectra WHERE id = ?), ?))
            """,
            (
                spectrum.id,
                spectrum.filename,
                str(array_path),
                json.dumps(spectrum.metadata),
                json.dumps(spectrum.preprocessing_history),
                spectrum.id,
                now,
            ),
        )
    return spectrum


def save_uploaded_spectrum(
    content: bytes,
    filename: str,
    metadata: dict[str, Any] | None = None,
    wavelength_column: str | int | None = None,
    intensity_column: str | int | None = None,
    filename_pattern: str | None = None,
    parse_filename_metadata: bool = True,
) -> Spectrum:
    """Parse and save uploaded spectrum bytes.

    Dispatches to the Excel reader for ``.xlsx``/``.xlsm``/``.xls`` filenames or
    when the first four bytes look like a ZIP/OLE2 container; otherwise treats
    the upload as text. Filename-derived metadata (pulse frequency, burst
    period, cycles, replicate) is merged in unless ``parse_filename_metadata``
    is False; user-supplied ``metadata`` values take precedence on conflict.
    """

    extension = Path(filename).suffix.lower()
    is_excel = extension in EXCEL_EXTENSIONS or _looks_like_binary_workbook(content)

    explicit_metadata = dict(metadata or {})
    auto_metadata: dict[str, Any] = {}
    if parse_filename_metadata:
        try:
            auto_metadata = extract_from_filename(filename, user_regex=filename_pattern)
        except re.error:
            auto_metadata = {}
    # User-supplied keys win over filename-derived ones.
    combined_metadata = {**auto_metadata, **explicit_metadata}

    if is_excel:
        spectrum = load_spectrum_excel(
            content,
            filename=filename,
            wavelength_column=wavelength_column,
            intensity_column=intensity_column,
            metadata=combined_metadata,
        )
    else:
        text = content.decode("utf-8-sig", errors="replace")
        spectrum = load_spectrum_text(
            text,
            filename=filename,
            wavelength_column=wavelength_column,
            intensity_column=intensity_column,
            metadata=combined_metadata,
        )
    return save_spectrum(spectrum)


def _looks_like_binary_workbook(content: bytes) -> bool:
    if not content:
        return False
    head = content[:4]
    # xlsx/xlsm are ZIP archives (PK\x03\x04); legacy .xls is OLE2 (D0 CF 11 E0).
    return head[:2] == b"PK" or head == b"\xd0\xcf\x11\xe0"


def get_spectrum(spectrum_id: str) -> Spectrum:
    """Load one spectrum by id."""

    initialize_storage()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM spectra WHERE id = ?", (spectrum_id,)).fetchone()
    if row is None:
        raise KeyError(f"spectrum not found: {spectrum_id}")
    frame = pd.read_csv(row["array_path"])
    return Spectrum(
        id=row["id"],
        filename=row["filename"],
        wavelength_nm=frame["wavelength_nm"].to_numpy(dtype=float),
        intensity=frame["intensity"].to_numpy(dtype=float),
        metadata=json.loads(row["metadata_json"]),
        preprocessing_history=json.loads(row["preprocessing_history_json"]),
    )


def list_spectra() -> list[dict[str, Any]]:
    """List stored spectra without loading full arrays."""

    initialize_storage()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM spectra ORDER BY created_at DESC").fetchall()
    summaries: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        history = json.loads(row["preprocessing_history_json"])
        try:
            frame = pd.read_csv(row["array_path"], usecols=["wavelength_nm"])
            points = len(frame)
            wl_min = float(frame["wavelength_nm"].min())
            wl_max = float(frame["wavelength_nm"].max())
        except Exception:
            points = None
            wl_min = None
            wl_max = None
        summaries.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "metadata": metadata,
                "preprocessing_history": history,
                "points": points,
                "wavelength_min_nm": wl_min,
                "wavelength_max_nm": wl_max,
                "created_at": row["created_at"],
            }
        )
    return summaries


def save_fit_result(result_id: str, result: dict[str, Any]) -> None:
    """Persist a fit result JSON blob for dashboard and exports."""

    initialize_storage()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO fit_results
            (id, spectrum_id, diagnostic, result_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                result.get("spectrum_id"),
                result.get("diagnostic", "analysis"),
                json.dumps(result),
                _now(),
            ),
        )


def list_fit_results() -> list[dict[str, Any]]:
    """Return stored fit results for dashboard plotting."""

    initialize_storage()
    with _connect() as conn:
        rows = conn.execute("SELECT result_json FROM fit_results ORDER BY created_at DESC").fetchall()
    return [json.loads(row["result_json"]) for row in rows]


def save_export_record(export_id: str, path: Path, kind: str) -> None:
    initialize_storage()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO exports (id, path, kind, created_at) VALUES (?, ?, ?, ?)",
            (export_id, str(path), kind, _now()),
        )


def get_export_path(export_id: str) -> Path:
    initialize_storage()
    with _connect() as conn:
        row = conn.execute("SELECT path FROM exports WHERE id = ?", (export_id,)).fetchone()
    if row is None:
        raise KeyError(f"export not found: {export_id}")
    return Path(row["path"])


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    # sqlite3.Connection's own context-manager protocol only commits/rolls
    # back a transaction -- it does NOT close the connection, so `with
    # _connect() as conn:` at every call site used to leak a connection
    # object, relying on CPython refcounting (not a language guarantee) to
    # eventually close it. Wrap it so every call site's `with` block still
    # reads the same but now actually closes on exit, and set a
    # busy_timeout so concurrent writers (e.g. a running batch plus a
    # recipe/spectrum save) back off and retry instead of immediately
    # raising "database is locked".
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
