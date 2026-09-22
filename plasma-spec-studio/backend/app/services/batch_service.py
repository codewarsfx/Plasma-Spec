"""Batch processing for applying recipes to many spectra.

Phase 4 expanded this module to dispatch on ``recipe_kind`` (set by the new
typed recipes) while preserving the original ``diagnostic`` fallback so legacy
saved recipes keep running.

For peak_list batches the output is *long-form*: one row per (file, peak),
so a recipe with N peaks across M spectra produces N*M rows. For
molecular_v2 / electron_density / legacy single-diagnostic batches the
output is one row per file.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.analysis.electron_density.orchestrator import compute_electron_density
from app.analysis.peaks.wavelength_list import analyze_peak_list
from app.core.fitting_utils import flatten_result_for_csv
from app.databases.molecular import store as molecular_store
from app.models.atomic_line_model import identify_lines
from app.models.hbeta_voigt_model import fit_hbeta
from app.models.molecular_band_model import (
    _resolve_transitions,
    fit_molecular_band,
    fit_molecular_state_by_state,
    fit_n2_cb,
    fit_oh_ax,
)
from app.models.peak_area_model import analyze_peak_window
from app.preprocessing.pipeline import apply_preprocessing_operations
from app.services.export_service import export_batch_csv, export_batch_xlsx
from app.services.spectrum_service import get_spectrum, save_fit_result


def run_batch(spectrum_ids: list[str], recipe: dict[str, Any]) -> dict[str, Any]:
    """Apply one recipe to many spectra and keep failures isolated.

    Returns a result envelope with completed/failed counts, per-spectrum
    results, a long-form ``rows`` list ready for CSV/XLSX export, and the
    written CSV + XLSX export records.
    """

    recipe_kind = _resolve_recipe_kind(recipe)
    results: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    completed = 0
    failed = 0

    for spectrum_id in spectrum_ids:
        try:
            spectrum = get_spectrum(spectrum_id)
            preprocessing = recipe.get("preprocessing") or []
            if preprocessing:
                spectrum = apply_preprocessing_operations(spectrum, preprocessing)
            result = _run_recipe_on_spectrum(spectrum, recipe, recipe_kind)
            save_fit_result(str(uuid4()), result)
            results.append(result)
            rows.extend(_long_form_rows(result, spectrum, recipe_kind))
            completed += 1
        except Exception as exc:
            failed += 1
            error_result = {
                "spectrum_id": spectrum_id,
                "filename": _safe_filename(spectrum_id),
                "diagnostic": recipe_kind,
                "recipe_kind": recipe_kind,
                "fit_quality": "bad",
                "warnings": [],
                "metrics": {},
                "parameters": {},
                "metadata": {},
                "error": str(exc),
            }
            results.append(error_result)
            rows.append(
                {
                    "spectrum_id": spectrum_id,
                    "filename": error_result["filename"],
                    "recipe_kind": recipe_kind,
                    "error": str(exc),
                    "fit_quality": "bad",
                }
            )

    csv_export = export_batch_csv(rows)
    xlsx_export = export_batch_xlsx(rows)
    return {
        "recipe_name": recipe.get("name"),
        "recipe_kind": recipe_kind,
        "completed": completed,
        "failed": failed,
        "results": results,
        "rows": rows,
        "exports": {"csv": csv_export, "xlsx": xlsx_export},
    }


def _resolve_recipe_kind(recipe: dict[str, Any]) -> str:
    """Pick the recipe kind, falling back to the legacy ``diagnostic`` field."""

    kind = recipe.get("recipe_kind")
    if kind:
        return str(kind)
    diagnostic = recipe.get("diagnostic")
    if not diagnostic:
        raise ValueError("recipe must specify either recipe_kind or diagnostic")
    return str(diagnostic)


def _run_recipe_on_spectrum(
    spectrum, recipe: dict[str, Any], recipe_kind: str
) -> dict[str, Any]:
    """Dispatch to the right analysis based on the recipe kind."""

    if recipe_kind == "peak_list":
        return _run_peak_list(spectrum, recipe)
    if recipe_kind == "molecular_v2":
        return _run_molecular_v2(spectrum, recipe)
    if recipe_kind == "electron_density":
        return _run_electron_density(spectrum, recipe)
    if recipe_kind == "line_identification":
        return _run_line_identification(spectrum, recipe)
    if recipe_kind in ("hbeta_voigt", "hbeta", "hbeta_gaussian", "hbeta_lorentzian"):
        return _run_legacy_hbeta(spectrum, recipe, recipe_kind)
    if recipe_kind == "peak_area":
        return _run_legacy_peak_area(spectrum, recipe)
    if recipe_kind == "oh_ax":
        return _run_legacy_oh(spectrum, recipe)
    if recipe_kind == "n2_cb":
        return _run_legacy_n2(spectrum, recipe)
    raise ValueError(f"unsupported recipe_kind: {recipe_kind!r}")


# --- Phase 4 dispatchers ---------------------------------------------------


def _run_peak_list(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    params = recipe.get("peak_list") or {}
    peaks_raw = params.get("peaks") or []
    if not peaks_raw:
        raise ValueError("peak_list recipe requires at least one peak in peak_list.peaks")
    peaks = [
        {key: value for key, value in entry.items() if value is not None}
        for entry in peaks_raw
    ]
    return analyze_peak_list(
        spectrum,
        peaks=peaks,
        default_half_width_nm=params.get("default_half_width_nm", 0.5),
        default_fit_model=params.get("default_fit_model"),
    )


def _run_molecular_v2(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    params = recipe.get("molecular") or {}
    species_id = params.get("species_id")
    if species_id not in molecular_store.SPECIES_REGISTRY:
        raise ValueError(f"unsupported species_id {species_id!r}")
    entry = molecular_store.SPECIES_REGISTRY[species_id]
    window_nm = params.get("window_nm") or list(entry.default_window_nm)
    from pathlib import Path

    demo_csv = (
        Path(__file__).resolve().parents[1]
        / "databases"
        / "molecular"
        / f"{species_id}"
        / "demo_transitions.csv"
    )
    transitions, source_label, demo = _resolve_transitions(
        species_id=species_id,
        window_nm=window_nm,
        explicit_path=None,
        database_source=params.get("database_source", "auto"),
        demo_csv=demo_csv,
    )
    if params.get("fit_mode") == "state_by_state":
        return fit_molecular_state_by_state(
            spectrum=spectrum,
            species_label=entry.label,
            diagnostic=f"molecular_state_{species_id.lower()}",
            window_nm=window_nm,
            transitions=transitions,
            instrument_fwhm_nm=params.get("instrument_fwhm_nm", 0.15),
            wavelength_shift_nm=params.get("wavelength_shift_nm", 0.0),
            demo_database=demo,
            database_source_label=source_label,
            max_states=params.get("max_states", 40),
            min_state_relative_strength=params.get("min_state_relative_strength", 0.0),
            wavelength_shift_bounds_nm=params.get("wavelength_shift_bounds_nm", (-2.0, 2.0)),
            instrument_fwhm_bounds_nm=params.get("instrument_fwhm_bounds_nm", (0.01, 2.0)),
            fit_wavelength_shift=params.get("fit_wavelength_shift", True),
            fit_instrument_fwhm=params.get("fit_instrument_fwhm", True),
            instrument_profile=params.get("instrument_profile", "gaussian"),
            instrument_lorentz_fwhm_nm=params.get("instrument_lorentz_fwhm_nm", 0.0),
        )
    return fit_molecular_band(
        spectrum=spectrum,
        species_label=entry.label,
        diagnostic=f"molecular_{species_id.lower()}",
        window_nm=window_nm,
        transitions=transitions,
        initial_trot_K=params.get("initial_trot_K", entry.typical_trot_K),
        trot_bounds_K=params.get("trot_bounds_K", (250.0, 8000.0)),
        instrument_fwhm_nm=params.get("instrument_fwhm_nm", 0.15),
        wavelength_shift_nm=params.get("wavelength_shift_nm", 0.0),
        demo_database=demo,
        database_source_label=source_label,
        tvib_enabled=False,
        wavelength_shift_bounds_nm=params.get("wavelength_shift_bounds_nm", (-2.0, 2.0)),
        instrument_fwhm_bounds_nm=params.get("instrument_fwhm_bounds_nm", (0.01, 2.0)),
        fit_tvib=params.get("fit_tvib", False),
        initial_tvib_K=params.get("initial_tvib_K"),
        tvib_bounds_K=params.get("tvib_bounds_K", (250.0, 10_000.0)),
        instrument_profile=params.get("instrument_profile", "gaussian"),
        instrument_lorentz_fwhm_nm=params.get("instrument_lorentz_fwhm_nm", 0.0),
        instrument_lorentz_fwhm_bounds_nm=params.get(
            "instrument_lorentz_fwhm_bounds_nm", (0.0, 1.0)
        ),
        fit_instrument_lorentz=params.get("fit_instrument_lorentz", False),
        multi_restart_trot_K=params.get("multi_restart_trot_K"),
    )


def _run_electron_density(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    params = recipe.get("electron_density") or {}
    if "Tg_K" not in params:
        raise ValueError("electron_density recipe requires electron_density.Tg_K")
    return compute_electron_density(
        spectrum,
        Tg_K=float(params["Tg_K"]),
        instrument_gauss_fwhm_nm=params.get("instrument_gauss_fwhm_nm", 0.13),
        line=params.get("line", "halpha"),
        model=params.get("model", "single_voigt"),
        window_nm=params.get("window_nm"),
        intensity_threshold_rel=params.get("intensity_threshold_rel", 0.05),
        center_initial_nm=params.get("center_initial_nm"),
        lorentz_initial_nm=params.get("lorentz_initial_nm", 1.0),
        lorentz2_initial_nm=params.get("lorentz2_initial_nm", 0.3),
        weight_initial=params.get("weight_initial", 0.7),
        center_bounds_nm=params.get("center_bounds_nm"),
        lorentz_bounds_nm=params.get("lorentz_bounds_nm", (0.0, 10.0)),
        Tg_uncertainty_K=params.get("Tg_uncertainty_K"),
    )


def _run_line_identification(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    fit_parameters = recipe.get("fit_parameters") or {}
    return identify_lines(
        spectrum,
        window_nm=recipe.get("window_nm"),
        threshold_rel=fit_parameters.get("threshold_rel", 0.1),
        tolerance_nm=fit_parameters.get("tolerance_nm", 0.25),
        species=fit_parameters.get("species"),
    )


# --- Legacy dispatchers (back-compat) --------------------------------------


def _run_legacy_hbeta(spectrum, recipe: dict[str, Any], recipe_kind: str) -> dict[str, Any]:
    fit_parameters = recipe.get("fit_parameters") or {}
    window_nm = recipe.get("window_nm")
    model = recipe.get("fit_model", "voigt")
    if recipe_kind == "hbeta_gaussian":
        model = "gaussian"
    elif recipe_kind == "hbeta_lorentzian":
        model = "lorentzian"
    return fit_hbeta(
        spectrum,
        window_nm=window_nm or (484.0, 488.0),
        model=model,
        center_bounds=fit_parameters.get("center_bounds", (485.8, 486.4)),
        sigma_bounds=fit_parameters.get("sigma_bounds", (0.001, 1.0)),
        gamma_bounds=fit_parameters.get("gamma_bounds", (0.001, 1.0)),
    )


def _run_legacy_peak_area(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    return analyze_peak_window(
        spectrum,
        window_nm=recipe.get("window_nm") or (484.0, 488.0),
        name=recipe.get("peak_name", "custom_peak"),
    )


def _run_legacy_oh(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    fp = recipe.get("fit_parameters") or {}
    return fit_oh_ax(
        spectrum,
        window_nm=recipe.get("window_nm") or (306.0, 312.0),
        initial_trot_K=fp.get("initial_trot_K", 1200.0),
        trot_bounds_K=fp.get("trot_bounds_K", (250.0, 6000.0)),
        instrument_fwhm_nm=fp.get("instrument_fwhm_nm", 0.12),
        wavelength_shift_nm=fp.get("wavelength_shift_nm", 0.0),
    )


def _run_legacy_n2(spectrum, recipe: dict[str, Any]) -> dict[str, Any]:
    fp = recipe.get("fit_parameters") or {}
    return fit_n2_cb(
        spectrum,
        window_nm=recipe.get("window_nm") or (334.0, 339.0),
        initial_trot_K=fp.get("initial_trot_K", 1000.0),
        trot_bounds_K=fp.get("trot_bounds_K", (250.0, 8000.0)),
        instrument_fwhm_nm=fp.get("instrument_fwhm_nm", 0.12),
        wavelength_shift_nm=fp.get("wavelength_shift_nm", 0.0),
    )


# --- Long-form row builder --------------------------------------------------


def _long_form_rows(
    result: dict[str, Any], spectrum, recipe_kind: str
) -> list[dict[str, Any]]:
    """Turn one analysis result into the row(s) it contributes to the batch table.

    peak_list results expand to one row per peak; everything else is one row.
    """

    base = {
        "spectrum_id": getattr(spectrum, "id", result.get("spectrum_id")),
        "filename": getattr(spectrum, "filename", result.get("filename")),
        "recipe_kind": recipe_kind,
    }
    metadata = result.get("metadata") or getattr(spectrum, "metadata", None) or {}
    for key, value in metadata.items():
        base[f"metadata_{key}"] = value

    if recipe_kind == "peak_list":
        rows: list[dict[str, Any]] = []
        for entry in result.get("results", []):
            row = dict(base)
            data = entry.get("data") or {}
            fit = entry.get("fit") or {}
            row.update(
                {
                    "peak_label": entry.get("label"),
                    "peak_species": entry.get("species"),
                    "requested_center_nm": entry.get("requested_center_nm"),
                    "search_half_width_nm": entry.get("search_half_width_nm"),
                    "fit_model": entry.get("fit_model"),
                    "fit_quality": entry.get("fit_quality"),
                    "warnings": "; ".join(entry.get("warnings") or []),
                    "data_peak_wavelength_nm": data.get("peak_wavelength_nm"),
                    "data_peak_height": data.get("peak_height_baseline_subtracted"),
                    "data_integrated_area": data.get("integrated_area"),
                    "data_baseline_subtracted_area": data.get("baseline_subtracted_area"),
                    "data_fwhm_nm": data.get("fwhm_data_nm"),
                    "data_snr": data.get("snr"),
                    "fit_center_nm": fit.get("center_nm"),
                    "fit_fwhm_nm": fit.get("fwhm_nm"),
                    "fit_area": fit.get("fit_area"),
                    "fit_r2": fit.get("r2"),
                    "fit_rmse": fit.get("rmse"),
                }
            )
            rows.append(row)
        return rows

    if recipe_kind == "molecular_v2":
        params = result.get("parameters") or {}
        stderr = result.get("parameter_stderr") or {}
        metrics = result.get("metrics") or {}
        row = dict(base)
        row.update(
            {
                "species": result.get("species"),
                "fit_quality": result.get("fit_quality"),
                "warnings": "; ".join(result.get("warnings") or []),
                "Trot_K": params.get("trot_K"),
                "Trot_stderr_K": stderr.get("trot_K"),
                "Tvib_K": params.get("tvib_K"),
                "Tvib_stderr_K": stderr.get("tvib_K"),
                "instrument_fwhm_nm": params.get("instrument_fwhm_nm"),
                "wavelength_shift_nm": params.get("wavelength_shift_nm"),
                "r2": metrics.get("r2"),
                "rmse": metrics.get("rmse"),
                "snr": metrics.get("snr"),
                "transition_count": result.get("transition_count"),
                "n_restarts": result.get("n_restarts"),
                "database_source": result.get("database_source"),
            }
        )
        return [row]

    if recipe_kind == "electron_density":
        ed = result.get("electron_density") or {}
        bd = result.get("fwhm_breakdown_nm") or {}
        ci = ed.get("confidence_interval_95") or {}
        params = result.get("parameters") or {}
        metrics = result.get("metrics") or {}
        row = dict(base)
        row.update(
            {
                "line": result.get("line"),
                "model": result.get("model"),
                "Tg_K": result.get("Tg_K"),
                "fit_quality": result.get("fit_quality"),
                "warnings": "; ".join(result.get("warnings") or []),
                "instrument_gauss_fwhm_nm": bd.get("instrument_gauss_fwhm_nm"),
                "lorentz_fwhm_nm": bd.get("lorentz_fwhm_nm") or bd.get("lorentz1_fwhm_nm"),
                "lorentz2_fwhm_nm": bd.get("lorentz2_fwhm_nm"),
                "vdw_fwhm_nm": bd.get("vdw_fwhm_nm"),
                "stark_fwhm_nm": bd.get("stark_fwhm_nm"),
                "electron_density_cm3": ed.get("electron_density_cm3"),
                "ne_lower_95_cm3": ci.get("lower_cm3"),
                "ne_upper_95_cm3": ci.get("upper_cm3"),
                "r2": metrics.get("r2"),
                "rmse": metrics.get("rmse"),
                "fit_center_nm": params.get("center_nm"),
                "calibration_validated": result.get("calibration_validated"),
            }
        )
        return [row]

    # Legacy / default: reuse flatten_result_for_csv.
    legacy_row = flatten_result_for_csv(result)
    legacy_row.update(base)
    return [legacy_row]


def _safe_filename(spectrum_id: str) -> str | None:
    try:
        return get_spectrum(spectrum_id).filename
    except Exception:
        return None
