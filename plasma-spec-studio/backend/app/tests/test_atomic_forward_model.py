from __future__ import annotations

import numpy as np

from app.core.spectrum import Spectrum
from app.models.atomic_forward_model import (
    atomic_species_templates,
    fit_atomic_forward_model,
    prepare_atomic_model_lines,
)


def test_atomic_forward_prepares_physics_ready_nist_lines():
    line_set = prepare_atomic_model_lines(
        species=["H I"],
        window_nm=(430.0, 660.0),
        temperature_K=9000.0,
        max_lines=1000,
        margin_nm=1.0,
    )

    assert line_set.available_count > 0
    assert line_set.physics_ready_count > 0
    assert line_set.used_count > 0
    assert {"A_ki_s_1", "E_k_cm1", "g_k"}.issubset(line_set.lines.columns)
    assert line_set.lines["A_ki_s_1"].notna().all()
    assert line_set.lines["E_k_cm1"].notna().all()
    assert line_set.lines["g_k"].notna().all()


def test_atomic_forward_fit_recovers_synthetic_temperature_shift_and_width():
    rng = np.random.default_rng(42)
    x = np.linspace(430.0, 660.0, 2301)
    true_temperature = 9500.0
    true_fwhm = 0.18
    true_shift = 0.035
    line_set = prepare_atomic_model_lines(
        species=["H I"],
        window_nm=(430.0, 660.0),
        temperature_K=true_temperature,
        max_lines=1000,
        margin_nm=2.0,
    )
    templates = atomic_species_templates(
        x,
        line_set.lines,
        species=["H I"],
        temperature_K=true_temperature,
        instrument_profile="gaussian",
        instrument_fwhm_nm=true_fwhm,
        instrument_lorentz_fwhm_nm=0.0,
        wavelength_shift_nm=true_shift,
    )
    y = 8.0 + 0.004 * (x - x.mean()) + 420.0 * templates["H I"]
    y = y + rng.normal(0.0, 0.7, size=len(x))
    spectrum = Spectrum("synthetic_h_atomic.csv", x, y)

    result = fit_atomic_forward_model(
        spectrum,
        species=["H I"],
        window_nm=(430.0, 660.0),
        initial_temperature_K=8000.0,
        temperature_bounds_K=(4000.0, 16_000.0),
        fit_temperature=True,
        instrument_fwhm_nm=0.12,
        instrument_fwhm_bounds_nm=(0.08, 0.35),
        fit_instrument_fwhm=True,
        wavelength_shift_nm=0.0,
        wavelength_shift_bounds_nm=(-0.2, 0.2),
        fit_wavelength_shift=True,
        max_lines=1000,
    )

    params = result["parameters"]
    assert result["diagnostic"] == "atomic_forward_model"
    assert result["metrics"]["r2"] > 0.98
    assert abs(params["temperature_K"] - true_temperature) < 650.0
    assert abs(params["instrument_fwhm_nm"] - true_fwhm) < 0.025
    assert abs(params["wavelength_shift_nm"] - true_shift) < 0.015
    assert result["line_contributions"]
