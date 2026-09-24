"""Spectrum, fit-result, and export persistence.

This module is a thin, backend-agnostic facade: every function delegates to
whichever ``Store`` is active for the current request (see
``app.services.backends.base.get_current_store``) -- local SQLite by
default, or Supabase when ``PLASMA_SPEC_STORAGE_BACKEND=supabase`` and a
request carries an authenticated user. Callers (routes, fitting_service,
batch_service, batch_manager, export_service, report_service) are unchanged
from before Supabase support existed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.spectrum import Spectrum
from app.preprocessing.filename_metadata import extract_from_filename
from app.preprocessing.importers import (
    EXCEL_EXTENSIONS,
    load_spectrum_excel,
    load_spectrum_text,
)
from app.services.backends.base import get_current_store
from app.services.backends.local_store import EXPORTS_DIR, SPECTRA_DIR, STORAGE_ROOT


__all__ = [
    "EXPORTS_DIR",
    "SPECTRA_DIR",
    "STORAGE_ROOT",
    "initialize_storage",
    "save_spectrum",
    "save_uploaded_spectrum",
    "get_spectrum",
    "list_spectra",
    "delete_spectrum",
    "save_fit_result",
    "list_fit_results",
    "save_export_record",
    "get_export_bytes",
]


def initialize_storage() -> None:
    get_current_store().initialize()


def save_spectrum(spectrum: Spectrum) -> Spectrum:
    """Persist a spectrum's array + metadata/history via the active store."""

    get_current_store().save_spectrum(spectrum)
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
    """Load one spectrum by id. Raises KeyError if not found."""

    return get_current_store().get_spectrum(spectrum_id)


def list_spectra() -> list[dict[str, Any]]:
    """List stored spectra without loading full arrays."""

    return get_current_store().list_spectra()


def delete_spectrum(spectrum_id: str) -> None:
    """Delete a spectrum and its associated fit results. Raises KeyError if
    not found."""

    get_current_store().delete_spectrum(spectrum_id)


def save_fit_result(result_id: str, result: dict[str, Any]) -> None:
    """Persist a fit result JSON blob for dashboard and exports."""

    get_current_store().save_fit_result(result_id, result)


def list_fit_results() -> list[dict[str, Any]]:
    """Return stored fit results for dashboard plotting."""

    return get_current_store().list_fit_results()


def save_export_record(export_id: str, path: Path, kind: str) -> None:
    get_current_store().save_export(export_id, kind, path)


def get_export_bytes(export_id: str) -> tuple[bytes, str]:
    """Return (content, filename) for a previously generated export."""

    return get_current_store().get_export_bytes(export_id)
