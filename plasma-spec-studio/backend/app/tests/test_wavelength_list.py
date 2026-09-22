from __future__ import annotations

import numpy as np

from app.analysis.peaks.wavelength_list import analyze_peak_list
from app.core.line_shapes import gaussian, lorentzian, voigt
from app.core.spectrum import Spectrum


def _build_three_peak_spectrum() -> Spectrum:
    rng = np.random.default_rng(7)
    x = np.linspace(300.0, 800.0, 10_001)
    centers = [310.0, 486.135, 656.279]
    amplitudes = [200.0, 150.0, 250.0]
    sigmas = [0.08, 0.05, 0.06]
    gammas = [0.04, 0.03, 0.04]
    y = 10.0 + 0.0005 * (x - 500.0)
    for c, a, s, g in zip(centers, amplitudes, sigmas, gammas):
        y = y + a * voigt(x, c, s, g)
    y = y + rng.normal(0.0, 0.1, size=len(x))
    return Spectrum("three_peaks.csv", x, y)


def test_data_only_metrics_recover_known_peak_locations():
    spectrum = _build_three_peak_spectrum()
    result = analyze_peak_list(
        spectrum,
        peaks=[
            {"label": "OH-like", "center_nm": 310.0, "half_width_nm": 1.0},
            {"label": "Hbeta", "center_nm": 486.135, "half_width_nm": 1.0},
            {"label": "Halpha", "center_nm": 656.279, "half_width_nm": 1.0},
        ],
    )
    assert len(result["results"]) == 3
    for entry, truth_center in zip(result["results"], (310.0, 486.135, 656.279)):
        data = entry["data"]
        assert data is not None
        assert abs(data["peak_wavelength_nm"] - truth_center) <= 0.05
        assert data["snr"] > 20
        assert entry["fit_quality"] == "good"
        assert entry["fit"] is None


def test_voigt_fit_recovers_center_and_fwhm():
    spectrum = _build_three_peak_spectrum()
    result = analyze_peak_list(
        spectrum,
        peaks=[
            {"label": "Hbeta", "center_nm": 486.135, "half_width_nm": 1.0, "fit_model": "voigt"},
        ],
    )
    entry = result["results"][0]
    fit = entry["fit"]
    assert fit is not None and fit["converged"]
    assert abs(fit["center_nm"] - 486.135) < 0.01
    # Voigt FWHM of sigma=0.05, gamma=0.03 is roughly 0.14 nm.
    assert 0.10 < fit["fwhm_nm"] < 0.20
    assert fit["r2"] > 0.99


def test_gaussian_fit_returns_gaussian_fwhm():
    rng = np.random.default_rng(13)
    x = np.linspace(740.0, 760.0, 4001)
    center = 750.0
    sigma = 0.07
    amplitude = 180.0
    y = 5.0 + amplitude * gaussian(x, center, sigma)
    y = y + rng.normal(0.0, 0.1, size=len(x))
    spectrum = Spectrum("gauss.csv", x, y)
    result = analyze_peak_list(
        spectrum,
        peaks=[
            {"label": "Ar-like", "center_nm": 750.0, "half_width_nm": 0.8, "fit_model": "gaussian"},
        ],
    )
    fit = result["results"][0]["fit"]
    assert fit is not None and fit["converged"]
    assert abs(fit["sigma_nm"] - sigma) < 0.01
    # Gaussian FWHM for sigma=0.07 is ~0.1648.
    assert abs(fit["fwhm_nm"] - 0.164) < 0.02


def test_lorentzian_fit_returns_lorentzian_fwhm():
    rng = np.random.default_rng(21)
    x = np.linspace(810.0, 815.0, 4001)
    center = 811.5
    gamma = 0.05
    amplitude = 220.0
    y = 6.0 + amplitude * lorentzian(x, center, gamma)
    y = y + rng.normal(0.0, 0.1, size=len(x))
    spectrum = Spectrum("lor.csv", x, y)
    result = analyze_peak_list(
        spectrum,
        peaks=[
            {"label": "Ar", "center_nm": 811.5, "half_width_nm": 0.8, "fit_model": "lorentzian"},
        ],
    )
    fit = result["results"][0]["fit"]
    assert fit is not None and fit["converged"]
    assert abs(fit["gamma_nm"] - gamma) < 0.01
    # Lorentzian FWHM = 2 gamma = 0.1.
    assert abs(fit["fwhm_nm"] - 0.10) < 0.02


def test_empty_window_returns_clean_failure():
    rng = np.random.default_rng(0)
    x = np.linspace(400.0, 500.0, 200)
    y = rng.normal(0.0, 1.0, size=len(x))
    spectrum = Spectrum("noise.csv", x, y)
    result = analyze_peak_list(
        spectrum,
        peaks=[{"label": "missing", "center_nm": 700.0, "half_width_nm": 0.5}],
    )
    entry = result["results"][0]
    assert entry["data"] is None
    assert entry["fit_quality"] == "bad"
    assert any("could not crop window" in warning for warning in entry["warnings"])
