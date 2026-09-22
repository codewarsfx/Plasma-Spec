"""Service layer for scientific fitting endpoints."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.analysis.electron_density.orchestrator import compute_electron_density
from app.analysis.peaks.wavelength_list import analyze_peak_list
from app.databases.molecular import store as molecular_store
from app.models.atomic_forward_model import fit_atomic_forward_model
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
from app.services.spectrum_service import get_spectrum, save_fit_result


def fit_hbeta_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    result = fit_hbeta(
        spectrum,
        window_nm=request.get("window_nm", (484.0, 488.0)),
        model=request.get("model", "voigt"),
        center_bounds=request.get("center_bounds", (485.8, 486.4)),
        sigma_bounds=request.get("sigma_bounds", (0.001, 1.0)),
        gamma_bounds=request.get("gamma_bounds", (0.001, 1.0)),
    )
    save_fit_result(str(uuid4()), result)
    return result


def fit_oh_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    result = fit_oh_ax(spectrum, **_molecular_kwargs(request, default_window=(306.0, 312.0), default_trot=1200.0))
    save_fit_result(str(uuid4()), result)
    return result


def fit_n2_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    result = fit_n2_cb(spectrum, **_molecular_kwargs(request, default_window=(334.0, 339.0), default_trot=1000.0))
    save_fit_result(str(uuid4()), result)
    return result


def _molecular_kwargs(
    request: dict[str, Any],
    default_window: tuple[float, float],
    default_trot: float,
) -> dict[str, Any]:
    """Translate the request payload into kwargs for fit_oh_ax / fit_n2_cb."""

    return {
        "window_nm": request.get("window_nm") or default_window,
        "initial_trot_K": request.get("initial_trot_K", default_trot),
        "trot_bounds_K": request.get("trot_bounds_K", (250.0, 6000.0)),
        "instrument_fwhm_nm": request.get("instrument_fwhm_nm", 0.12),
        "wavelength_shift_nm": request.get("wavelength_shift_nm", 0.0),
        "database_source": request.get("database_source", "auto"),
        "wavelength_shift_bounds_nm": request.get("wavelength_shift_bounds_nm", (-2.0, 2.0)),
        "instrument_fwhm_bounds_nm": request.get("instrument_fwhm_bounds_nm", (0.01, 2.0)),
        "fit_tvib": request.get("fit_tvib", False),
        "initial_tvib_K": request.get("initial_tvib_K"),
        "tvib_bounds_K": request.get("tvib_bounds_K", (250.0, 10_000.0)),
        "instrument_profile": request.get("instrument_profile", "gaussian"),
        "instrument_lorentz_fwhm_nm": request.get("instrument_lorentz_fwhm_nm", 0.0),
        "instrument_lorentz_fwhm_bounds_nm": request.get("instrument_lorentz_fwhm_bounds_nm", (0.0, 1.0)),
        "fit_instrument_lorentz": request.get("fit_instrument_lorentz", False),
        "multi_restart_trot_K": request.get("multi_restart_trot_K"),
    }


def fit_molecular_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Unified molecular fit driver for any species registered in the store."""

    from pathlib import Path

    spectrum = _prepare_spectrum(spectrum_id, request)

    species_id = request["species_id"]
    if species_id not in molecular_store.SPECIES_REGISTRY:
        raise ValueError(f"unknown species_id: {species_id!r}")
    entry = molecular_store.SPECIES_REGISTRY[species_id]

    window_nm = request.get("window_nm") or list(entry.default_window_nm)
    demo_csv = Path(__file__).resolve().parents[1] / "databases" / "molecular" / f"{species_id}" / "demo_transitions.csv"

    transitions, source_label, demo = _resolve_transitions(
        species_id=species_id,
        window_nm=window_nm,
        explicit_path=None,
        database_source=request.get("database_source", "auto"),
        demo_csv=demo_csv,
    )

    result = fit_molecular_band(
        spectrum=spectrum,
        species_label=entry.label,
        diagnostic=f"molecular_{species_id.lower()}",
        window_nm=window_nm,
        transitions=transitions,
        initial_trot_K=request.get("initial_trot_K", entry.typical_trot_K),
        trot_bounds_K=request.get("trot_bounds_K", (250.0, 8000.0)),
        instrument_fwhm_nm=request.get("instrument_fwhm_nm", 0.12),
        wavelength_shift_nm=request.get("wavelength_shift_nm", 0.0),
        demo_database=demo,
        database_source_label=source_label,
        wavelength_shift_bounds_nm=request.get("wavelength_shift_bounds_nm", (-2.0, 2.0)),
        instrument_fwhm_bounds_nm=request.get("instrument_fwhm_bounds_nm", (0.01, 2.0)),
        fit_tvib=request.get("fit_tvib", False),
        initial_tvib_K=request.get("initial_tvib_K"),
        tvib_bounds_K=request.get("tvib_bounds_K", (250.0, 10_000.0)),
        instrument_profile=request.get("instrument_profile", "gaussian"),
        instrument_lorentz_fwhm_nm=request.get("instrument_lorentz_fwhm_nm", 0.0),
        instrument_lorentz_fwhm_bounds_nm=request.get("instrument_lorentz_fwhm_bounds_nm", (0.0, 1.0)),
        fit_instrument_lorentz=request.get("fit_instrument_lorentz", False),
        multi_restart_trot_K=request.get("multi_restart_trot_K"),
    )
    save_fit_result(str(uuid4()), result)
    return result


def fit_molecular_state_by_state_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Unified state-by-state molecular fit for any registered species."""

    from pathlib import Path

    spectrum = _prepare_spectrum(spectrum_id, request)

    species_id = request["species_id"]
    if species_id not in molecular_store.SPECIES_REGISTRY:
        raise ValueError(f"unknown species_id: {species_id!r}")
    entry = molecular_store.SPECIES_REGISTRY[species_id]
    window_nm = request.get("window_nm") or list(entry.default_window_nm)
    demo_csv = Path(__file__).resolve().parents[1] / "databases" / "molecular" / f"{species_id}" / "demo_transitions.csv"

    transitions, source_label, demo = _resolve_transitions(
        species_id=species_id,
        window_nm=window_nm,
        explicit_path=None,
        database_source=request.get("database_source", "auto"),
        demo_csv=demo_csv,
    )

    result = fit_molecular_state_by_state(
        spectrum=spectrum,
        species_label=entry.label,
        diagnostic=f"molecular_state_{species_id.lower()}",
        window_nm=window_nm,
        transitions=transitions,
        instrument_fwhm_nm=request.get("instrument_fwhm_nm", 0.12),
        wavelength_shift_nm=request.get("wavelength_shift_nm", 0.0),
        demo_database=demo,
        database_source_label=source_label,
        max_states=request.get("max_states", 40),
        min_state_relative_strength=request.get("min_state_relative_strength", 0.0),
        wavelength_shift_bounds_nm=request.get("wavelength_shift_bounds_nm", (-2.0, 2.0)),
        instrument_fwhm_bounds_nm=request.get("instrument_fwhm_bounds_nm", (0.01, 2.0)),
        fit_wavelength_shift=request.get("fit_wavelength_shift", True),
        fit_instrument_fwhm=request.get("fit_instrument_fwhm", True),
        instrument_profile=request.get("instrument_profile", "gaussian"),
        instrument_lorentz_fwhm_nm=request.get("instrument_lorentz_fwhm_nm", 0.0),
    )
    save_fit_result(str(uuid4()), result)
    return result


def fit_atomic_forward_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """NIST-backed relative atomic forward-model fit."""

    spectrum = _prepare_spectrum(spectrum_id, request)
    result = fit_atomic_forward_model(
        spectrum,
        species=request.get("species") or ["H I", "Ar I", "O I", "N II"],
        window_nm=request.get("window_nm", (300.0, 900.0)),
        initial_temperature_K=request.get("initial_temperature_K", 9000.0),
        temperature_bounds_K=request.get("temperature_bounds_K", (1000.0, 30_000.0)),
        fit_temperature=request.get("fit_temperature", True),
        instrument_profile=request.get("instrument_profile", "gaussian"),
        instrument_fwhm_nm=request.get("instrument_fwhm_nm", 0.15),
        instrument_fwhm_bounds_nm=request.get("instrument_fwhm_bounds_nm", (0.02, 2.0)),
        fit_instrument_fwhm=request.get("fit_instrument_fwhm", True),
        instrument_lorentz_fwhm_nm=request.get("instrument_lorentz_fwhm_nm", 0.0),
        instrument_lorentz_fwhm_bounds_nm=request.get("instrument_lorentz_fwhm_bounds_nm", (0.0, 2.0)),
        fit_instrument_lorentz=request.get("fit_instrument_lorentz", False),
        wavelength_shift_nm=request.get("wavelength_shift_nm", 0.0),
        wavelength_shift_bounds_nm=request.get("wavelength_shift_bounds_nm", (-1.0, 1.0)),
        fit_wavelength_shift=request.get("fit_wavelength_shift", True),
        species_weights=request.get("species_weights") or {},
        fit_species_scales=request.get("fit_species_scales", True),
        baseline_order=request.get("baseline_order", 1),
        max_lines=request.get("max_lines", 3000),
        top_contributions=request.get("top_contributions", 40),
    )
    save_fit_result(str(uuid4()), result)
    return result


def analyze_peak_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    result = analyze_peak_window(
        spectrum,
        window_nm=request.get("window_nm", (484.0, 488.0)),
        name=request.get("name", "custom_peak"),
    )
    save_fit_result(str(uuid4()), result)
    return result


def compute_electron_density_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    result = compute_electron_density(
        spectrum,
        Tg_K=float(request["Tg_K"]),
        instrument_gauss_fwhm_nm=request.get("instrument_gauss_fwhm_nm", 0.13),
        line=request.get("line", "halpha"),
        model=request.get("model", "single_voigt"),
        window_nm=request.get("window_nm"),
        intensity_threshold_rel=request.get("intensity_threshold_rel", 0.05),
        center_initial_nm=request.get("center_initial_nm"),
        lorentz_initial_nm=request.get("lorentz_initial_nm", 1.0),
        lorentz2_initial_nm=request.get("lorentz2_initial_nm", 0.3),
        weight_initial=request.get("weight_initial", 0.7),
        center_bounds_nm=request.get("center_bounds_nm"),
        lorentz_bounds_nm=request.get("lorentz_bounds_nm", (0.0, 10.0)),
        Tg_uncertainty_K=request.get("Tg_uncertainty_K"),
    )
    save_fit_result(str(uuid4()), result)
    return result


def analyze_peak_list_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    raw_peaks = request.get("peaks") or []
    peaks = [
        {key: value for key, value in entry.items() if value is not None}
        for entry in raw_peaks
    ]
    if not peaks:
        raise ValueError("at least one peak must be provided in 'peaks'")
    result = analyze_peak_list(
        spectrum,
        peaks=peaks,
        default_half_width_nm=request.get("default_half_width_nm", 0.5),
        default_fit_model=request.get("default_fit_model"),
    )
    save_fit_result(str(uuid4()), result)
    return result


def identify_lines_by_id(spectrum_id: str, request: dict[str, Any]) -> dict[str, Any]:
    spectrum = _prepare_spectrum(spectrum_id, request)
    return identify_lines(
        spectrum,
        window_nm=request.get("window_nm"),
        threshold_rel=request.get("threshold_rel", 0.1),
        tolerance_nm=request.get("tolerance_nm", 0.25),
    )


def _prepare_spectrum(spectrum_id: str, request: dict[str, Any]):
    spectrum = get_spectrum(spectrum_id)
    preprocessing = request.get("preprocessing") or []
    if preprocessing:
        spectrum = apply_preprocessing_operations(spectrum, preprocessing)
    return spectrum
