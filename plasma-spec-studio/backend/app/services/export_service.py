"""Export helpers for fit results, spectra, and batch tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from app.core.constants import SOFTWARE_VERSION
from app.core.fitting_utils import flatten_result_for_csv
from app.core.spectrum import Spectrum
from app.services.spectrum_service import EXPORTS_DIR, save_export_record


def export_result_json(result: dict[str, Any]) -> dict[str, Any]:
    """Write one result JSON file and register it."""

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}.json"
    payload = _with_export_metadata(result)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    save_export_record(export_id, path, "json")
    return {"export_id": export_id, "path": str(path), "kind": "json"}


def export_result_csv(result: dict[str, Any]) -> dict[str, Any]:
    """Write one result CSV row and register it."""

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}.csv"
    pd.DataFrame([flatten_result_for_csv(result)]).to_csv(path, index=False)
    save_export_record(export_id, path, "csv")
    return {"export_id": export_id, "path": str(path), "kind": "csv"}


def export_batch_csv(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write a long-form batch results table to CSV.

    Accepts either raw long-form rows (dicts with explicit columns) or
    legacy result dicts (auto-flattened via ``flatten_result_for_csv``).
    """

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_batch.csv"
    frame_rows = _normalize_rows(rows)
    pd.DataFrame(frame_rows).to_csv(path, index=False)
    save_export_record(export_id, path, "csv")
    return {"export_id": export_id, "path": str(path), "kind": "csv"}


def export_batch_xlsx(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write a long-form batch results table to XLSX (one sheet 'results')."""

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_batch.xlsx"
    frame_rows = _normalize_rows(rows)
    frame = pd.DataFrame(frame_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="results", index=False)
    save_export_record(export_id, path, "xlsx")
    return {"export_id": export_id, "path": str(path), "kind": "xlsx"}


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect whether rows are raw long-form or legacy result dicts and adapt."""

    if not rows:
        return []
    sample = rows[0]
    # Long-form rows have explicit scalar columns (no nested 'parameters' key);
    # legacy result dicts have 'parameters'/'metrics' as nested dicts.
    if any(isinstance(value, dict) for value in sample.values()):
        return [flatten_result_for_csv(row) for row in rows]
    return rows


def export_processed_spectrum_csv(spectrum: Spectrum) -> dict[str, Any]:
    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_processed_spectrum.csv"
    frame = pd.DataFrame({"wavelength_nm": spectrum.wavelength_nm, "intensity": spectrum.intensity})
    frame.to_csv(path, index=False)
    save_export_record(export_id, path, "csv")
    return {"export_id": export_id, "path": str(path), "kind": "csv"}


def export_fit_plot_png(result: dict[str, Any]) -> dict[str, Any]:
    """Create a PNG of measured vs fit and residuals.

    Matplotlib is imported lazily so the scientific tests do not require the
    plotting dependency.
    """

    import matplotlib.pyplot as plt

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_fit.png"
    measured = result.get("measured_curve") or []
    fit_curve = result.get("fit_curve") or []
    residual = result.get("residual_curve") or []
    fig, axes = plt.subplots(2, 1, figsize=(7, 5), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    if measured:
        axes[0].plot([p["wavelength_nm"] for p in measured], [p["value"] for p in measured], label="Measured")
    if fit_curve:
        axes[0].plot([p["wavelength_nm"] for p in fit_curve], [p["value"] for p in fit_curve], label="Fit")
    if residual:
        axes[1].plot([p["wavelength_nm"] for p in residual], [p["value"] for p in residual], color="crimson")
    axes[0].set_ylabel("Intensity (a.u.)")
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Residual")
    axes[0].legend()
    axes[0].set_title(f"{result.get('filename', '')} - {result.get('diagnostic', '')}")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    save_export_record(export_id, path, "png")
    return {"export_id": export_id, "path": str(path), "kind": "png"}


def _with_export_metadata(result: dict[str, Any]) -> dict[str, Any]:
    return {
        **result,
        "software_version": SOFTWARE_VERSION,
        "export_note": "Exports include demo database warnings when demo molecular data are used.",
    }

