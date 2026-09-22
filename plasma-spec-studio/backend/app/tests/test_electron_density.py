"""Tests for the Stark / Gigosos electron-density workflow.

The Gigosos formula and the vdW correction are tested against hand-computed
values (so we catch any drift from the lab MATLAB), then we round-trip:
synthesize a Voigt at a known Lorentzian width, fit it, check that the fit
recovers the width and that the n_e back-calculation lands within a few
percent of the truth.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.analysis.electron_density.orchestrator import compute_electron_density
from app.analysis.electron_density.stark_calibration import (
    HALPHA_LAB,
    HBETA_CROSSCHECK,
    electron_density_cm3,
    two_population_electron_density,
    van_der_waals_fwhm_nm,
)
from app.analysis.electron_density.voigt_fits import (
    fit_single_voigt_halpha,
    fit_two_voigt_halpha,
    two_voigt_unit_peak,
    voigt_unit_peak,
)
from app.core.spectrum import Spectrum


# --- Stark calibration (MATLAB parity) --------------------------------------


def test_van_der_waals_matches_matlab_formula():
    # Ne.m line 3: w_vdw = 5.12 / Tg^0.7
    for Tg in (300.0, 500.0, 650.0, 1000.0, 1500.0):
        expected = 5.12 / Tg**0.7
        assert van_der_waals_fwhm_nm(Tg, HALPHA_LAB) == pytest.approx(expected, rel=1e-12)


def test_van_der_waals_zero_for_hbeta_crosscheck():
    """We zero out vdW for the H-beta cross-check (lab does not use it there)."""

    assert van_der_waals_fwhm_nm(650.0, HBETA_CROSSCHECK) == 0.0


def test_electron_density_matches_matlab_recipe():
    # Reference: Tg=650 K, wL=0.5 nm  ->  n_e = 1.250e16 cm^-3
    result = electron_density_cm3(0.5, 650.0, HALPHA_LAB)
    assert result["vdw_fwhm_nm"] == pytest.approx(5.12 / 650**0.7, rel=1e-12)
    expected_stark = 0.5 - result["vdw_fwhm_nm"]
    assert result["stark_fwhm_nm"] == pytest.approx(expected_stark, rel=1e-12)
    expected_ne = (expected_stark / 1.78) ** 1.5 * 1e17
    assert result["electron_density_cm3"] == pytest.approx(expected_ne, rel=1e-12)


def test_electron_density_warns_when_stark_negative():
    """If Lorentzian FWHM is below the vdW contribution, n_e is not computable."""

    Tg = 650.0
    wvdw = 5.12 / Tg**0.7
    result = electron_density_cm3(wvdw * 0.5, Tg, HALPHA_LAB)
    assert result["electron_density_cm3"] is None
    assert result["warning"] is not None
    assert "Stark FWHM" in result["warning"]


def test_two_population_weighted_n_e():
    Tg = 650.0
    ne1 = electron_density_cm3(1.0, Tg, HALPHA_LAB)["electron_density_cm3"]
    ne2 = electron_density_cm3(0.3, Tg, HALPHA_LAB)["electron_density_cm3"]
    expected = 0.7 * ne1 + 0.3 * ne2

    combined = two_population_electron_density(1.0, 0.3, 0.7, Tg, HALPHA_LAB)
    assert combined["electron_density_cm3"] == pytest.approx(expected, rel=1e-12)


def test_two_population_weight_validation():
    with pytest.raises(ValueError):
        two_population_electron_density(1.0, 0.3, 1.2, 650.0, HALPHA_LAB)


# --- Voigt unit-peak parity with MATLAB convention --------------------------


def test_voigt_unit_peak_max_equals_one():
    x = np.linspace(655.0, 657.5, 4001)
    profile = voigt_unit_peak(x, 656.279, wL_nm=0.5, wg_nm=0.13)
    assert profile.max() == pytest.approx(1.0, abs=1e-10)
    # peak should sit at center
    assert abs(x[int(np.argmax(profile))] - 656.279) < 0.01


def test_two_voigt_unit_peak_max_equals_one():
    x = np.linspace(655.5, 657.0, 4001)
    profile = two_voigt_unit_peak(x, 656.279, wL1_nm=1.2, wL2_nm=0.3, wg_nm=0.13, a=0.7)
    assert profile.max() == pytest.approx(1.0, abs=1e-10)


# --- Round-trip: known wL -> fit -> wL ------------------------------------


def _synthesize_halpha(
    wL_nm: float,
    wg_nm: float,
    *,
    n_points: int = 4001,
    baseline: float = 5.0,
    amplitude: float = 1000.0,
    noise: float = 0.5,
    seed: int = 0,
    wavelength_range_nm: tuple[float, float] = (600.0, 700.0),
) -> Spectrum:
    """Synthesize an H-alpha spectrum.

    The default 600-700 nm wavelength range matches the lab MATLAB so the
    (I - min) / (max - min) normalization sees true line wings decaying to
    the noise baseline.
    """

    rng = np.random.default_rng(seed)
    x = np.linspace(wavelength_range_nm[0], wavelength_range_nm[1], n_points)
    profile = voigt_unit_peak(x, 656.279, wL_nm, wg_nm)
    y = baseline + amplitude * profile + rng.normal(0.0, noise, size=len(x))
    return Spectrum("halpha_synth.csv", x, y)


def test_single_voigt_fit_recovers_known_lorentz_width_no_threshold():
    """With no intensity threshold the Voigt math recovers the truth tightly.

    This isolates the fit algorithm from the lab's (I - min) / (max - min)
    procedural quirk so we can verify the math itself.
    """

    spectrum = _synthesize_halpha(wL_nm=0.50, wg_nm=0.13)
    result = fit_single_voigt_halpha(
        spectrum.wavelength_nm,
        spectrum.intensity,
        window_nm=(652.0, 660.0),
        instrument_gauss_fwhm_nm=0.13,
        intensity_threshold_rel=0.0,
    )
    assert abs(result["parameters"]["lorentz_fwhm_nm"] - 0.50) < 0.01
    assert abs(result["parameters"]["center_nm"] - 656.279) < 0.005
    assert result["fit_metrics"]["r2"] > 0.999


def test_single_voigt_fit_with_lab_default_threshold_is_loosely_accurate():
    """Documents the ~10% systematic bias the lab procedure introduces.

    The (I - min) / (max - min) normalization after the 5% intensity cut
    pins the wings to zero, which biases the Lorentzian width slightly low
    on clean synthetic data. On real noisy data this is masked by noise and
    is part of the procedure's accepted precision.
    """

    spectrum = _synthesize_halpha(wL_nm=0.50, wg_nm=0.13)
    result = fit_single_voigt_halpha(
        spectrum.wavelength_nm,
        spectrum.intensity,
        window_nm=(652.0, 660.0),
        instrument_gauss_fwhm_nm=0.13,
        intensity_threshold_rel=0.05,
    )
    fit_wL = result["parameters"]["lorentz_fwhm_nm"]
    # Lab procedure typically biases wL down by ~5-15% on bright clean lines.
    assert 0.40 < fit_wL < 0.55, f"unexpected lab-procedure bias: wL_fit={fit_wL}"


def test_single_voigt_fit_recovers_narrow_line_no_threshold():
    spectrum = _synthesize_halpha(wL_nm=0.10, wg_nm=0.13)
    result = fit_single_voigt_halpha(
        spectrum.wavelength_nm,
        spectrum.intensity,
        window_nm=(654.0, 658.5),
        instrument_gauss_fwhm_nm=0.13,
        intensity_threshold_rel=0.0,
    )
    assert abs(result["parameters"]["lorentz_fwhm_nm"] - 0.10) < 0.02


def test_two_voigt_fit_recovers_known_two_populations_no_threshold():
    rng = np.random.default_rng(42)
    x = np.linspace(650.0, 663.0, 6001)
    wL1, wL2, a = 1.20, 0.30, 0.65
    profile = two_voigt_unit_peak(x, 656.28, wL1, wL2, 0.13, a)
    y = 5.0 + 800.0 * profile + rng.normal(0.0, 0.5, size=len(x))

    result = fit_two_voigt_halpha(
        x, y,
        window_nm=(652.0, 660.5),
        instrument_gauss_fwhm_nm=0.13,
        intensity_threshold_rel=0.0,
    )
    params = result["parameters"]
    # The two-Voigt landscape is shallow; widths recover to ~10% and weight to ~10pp.
    assert abs(params["lorentz1_fwhm_nm"] - wL1) < 0.2
    assert abs(params["lorentz2_fwhm_nm"] - wL2) < 0.1
    assert abs(params["weight_pop1"] - a) < 0.10
    assert result["fit_metrics"]["r2"] > 0.995


def test_end_to_end_electron_density_round_trip_with_lab_procedure():
    """End-to-end run of the full lab procedure (5% threshold + normalization).

    Documents the procedural bias: on a perfectly clean synthetic Voigt the
    (I - min) / (max - min) normalization after the 5% intensity cut systematically
    underestimates n_e by up to ~20% because the line wings inside the retained
    points are pinned to zero rather than to their true small-but-positive value.
    On real spectra this bias is masked by noise floor variation. Recovery within
    25% is the realistic bound for clean synthetic data via the lab procedure.
    """

    Tg = 650.0
    target_ne = 1.0e16
    wS = 1.78 * (target_ne / 1e17) ** (2.0 / 3.0)
    wvdW = 5.12 / Tg**0.7
    wL = wS + wvdW

    spectrum = _synthesize_halpha(wL_nm=wL, wg_nm=0.13)
    result = compute_electron_density(
        spectrum,
        Tg_K=Tg,
        instrument_gauss_fwhm_nm=0.13,
        line="halpha",
        model="single_voigt",
        # default lab settings
    )
    ne_fit = result["electron_density"]["electron_density_cm3"]
    assert ne_fit is not None
    assert abs(ne_fit - target_ne) / target_ne < 0.25, (
        f"recovered n_e {ne_fit:.2e}, target {target_ne:.2e} - lab procedural bias should be < 25%"
    )


def test_end_to_end_electron_density_round_trip_no_threshold():
    """Tight round-trip with no intensity threshold proves the math is exact.

    Recovers n_e at high density (5e16 cm^-3) to better than 5% when the
    procedural threshold is disabled.
    """

    Tg = 650.0
    target_ne = 5.0e16
    wS = 1.78 * (target_ne / 1e17) ** (2.0 / 3.0)
    wvdW = 5.12 / Tg**0.7
    wL = wS + wvdW

    spectrum = _synthesize_halpha(wL_nm=wL, wg_nm=0.13)
    result = compute_electron_density(
        spectrum,
        Tg_K=Tg,
        instrument_gauss_fwhm_nm=0.13,
        line="halpha",
        model="single_voigt",
        intensity_threshold_rel=0.0,
    )
    ne_fit = result["electron_density"]["electron_density_cm3"]
    assert ne_fit is not None
    assert abs(ne_fit - target_ne) / target_ne < 0.05


def test_end_to_end_reports_all_intermediate_values():
    spectrum = _synthesize_halpha(wL_nm=0.50, wg_nm=0.13)
    result = compute_electron_density(
        spectrum,
        Tg_K=650.0,
        instrument_gauss_fwhm_nm=0.13,
        line="halpha",
        model="single_voigt",
        window_nm=(652.0, 660.0),
    )
    breakdown = result["fwhm_breakdown_nm"]
    # The original spec demands traceability: every intermediate value must be present.
    for key in (
        "instrument_gauss_fwhm_nm",
        "lorentz_fwhm_nm",
        "vdw_fwhm_nm",
        "stark_fwhm_nm",
        "voigt_total_fwhm_nm",
    ):
        assert key in breakdown
    assert result["electron_density"]["confidence_interval_95"]["lower_cm3"] is not None
    assert result["electron_density"]["confidence_interval_95"]["upper_cm3"] is not None


def test_hbeta_crosscheck_flagged_unvalidated():
    spectrum = _synthesize_halpha(wL_nm=0.5, wg_nm=0.13)
    # We can synthesize at any wavelength; the H-beta calibration just changes the
    # Stark constant. Override the window so the fit can still find the line.
    result = compute_electron_density(
        spectrum,
        Tg_K=650.0,
        instrument_gauss_fwhm_nm=0.13,
        line="hbeta",
        model="single_voigt",
        window_nm=(652.0, 660.0),
        center_initial_nm=656.279,
        center_bounds_nm=(650.0, 660.0),
    )
    assert result["calibration_validated"] is False
    assert any("not validated" in w for w in result["warnings"])
