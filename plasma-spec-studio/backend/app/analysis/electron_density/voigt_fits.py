"""Single-Voigt and Two-Voigt H-alpha fitters - faithful port of the lab MATLAB.

The MATLAB workflow is:

    1. Crop to a window around the H-alpha line.
    2. Drop points where I < 5% of I_max (denoise the wings).
    3. Normalize: I_norm = (I - min) / (max - min).  Peak then equals 1.
    4. Fit a unit-peak Voigt (or two-population Voigt) with a *fixed* Gaussian
       FWHM (combined instrumental + Doppler) and free Lorentzian FWHM and
       line center.

The lab's Voigt definition (Voigt.m) numerically integrates the
Gaussian-Lorentzian convolution and then divides by the maximum of the result
to give a unit-peak profile. This module uses ``scipy.special.wofz`` for the
analytic Voigt - identical mathematically, much faster - and normalizes by the
profile maximum to preserve the lab convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import wofz


SQRT_LN2 = math.sqrt(math.log(2.0))
TWO_SQRT_LN2 = 2.0 * SQRT_LN2


def _sigma_from_gauss_fwhm(wg_nm: float) -> float:
    """Convert Gaussian FWHM (the MATLAB parameter ``wg``) to sigma."""

    return wg_nm / (2.0 * math.sqrt(2.0 * math.log(2.0)))


def voigt_unit_peak(
    x: np.ndarray, x0: float, wL_nm: float, wg_nm: float
) -> np.ndarray:
    """Unit-peak Voigt profile matching the lab MATLAB ``Voigt.m`` convention.

    ``wL_nm`` is the Lorentzian FWHM (the parameter ``wL`` in Voigt.m).
    ``wg_nm`` is the Gaussian FWHM (the parameter ``wg`` in Voigt.m).
    The Voigt profile is computed via ``scipy.special.wofz`` and then divided
    by its own maximum on the grid so the peak equals 1, mirroring
    ``IV = IV / max(IV)`` in the MATLAB source.
    """

    x_arr = np.asarray(x, dtype=float)
    sigma = _sigma_from_gauss_fwhm(wg_nm)
    gamma = max(float(wL_nm) / 2.0, 1e-12)
    z = ((x_arr - float(x0)) + 1j * gamma) / (sigma * math.sqrt(2.0))
    profile = np.real(wofz(z))
    peak = profile.max()
    if peak <= 0:
        return np.zeros_like(x_arr)
    return profile / peak


def two_voigt_unit_peak(
    x: np.ndarray,
    x0: float,
    wL1_nm: float,
    wL2_nm: float,
    wg_nm: float,
    a: float,
) -> np.ndarray:
    """Two-population unit-peak Voigt matching ``TwoVoigt.m``.

    ``a`` is the fractional weight of the wL1 population (``1 - a`` of wL2).
    The two profiles share the same center ``x0`` and the same Gaussian FWHM
    ``wg``. The combined profile is normalized by its own peak.
    """

    v1 = voigt_unit_peak(x, x0, wL1_nm, wg_nm)
    v2 = voigt_unit_peak(x, x0, wL2_nm, wg_nm)
    combined = a * v1 + (1.0 - a) * v2
    peak = combined.max()
    if peak <= 0:
        return combined
    return combined / peak


@dataclass(slots=True)
class _PreparedData:
    """Window-cropped, threshold-filtered, peak-normalized data ready for fit."""

    x_nm: np.ndarray
    I_norm: np.ndarray
    I_min: float
    I_max: float
    n_used: int
    n_dropped: int


def _prepare_halpha_data(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    window_nm: tuple[float, float],
    intensity_threshold_rel: float,
) -> _PreparedData:
    """Match the MATLAB pre-fit pipeline exactly.

    Crops to ``window_nm``, drops points where ``I < threshold * I_max``, then
    normalizes ``I_norm = (I - min) / (max - min)``. The peak is rescaled to 1
    so the fit only needs to determine widths and center, matching
    ``ElectronDensity.m`` line 23.
    """

    x = np.asarray(wavelength_nm, dtype=float)
    y = np.asarray(intensity, dtype=float)
    lo, hi = float(window_nm[0]), float(window_nm[1])
    if lo >= hi:
        raise ValueError("window must be ordered low < high")
    window_mask = (x >= lo) & (x <= hi)
    if window_mask.sum() < 5:
        raise ValueError("electron-density window contains fewer than 5 points")
    x_win = x[window_mask]
    y_win = y[window_mask]

    threshold = float(intensity_threshold_rel) * float(np.max(y_win))
    keep_mask = y_win > threshold
    if keep_mask.sum() < 5:
        raise ValueError(
            "fewer than 5 points above the intensity threshold; lower the threshold "
            "or check the spectrum"
        )
    x_filt = x_win[keep_mask]
    y_filt = y_win[keep_mask]

    y_min = float(np.min(y_filt))
    y_max = float(np.max(y_filt))
    if y_max <= y_min:
        raise ValueError("intensities are flat after thresholding; fit not possible")
    y_norm = (y_filt - y_min) / (y_max - y_min)

    return _PreparedData(
        x_nm=x_filt,
        I_norm=y_norm,
        I_min=y_min,
        I_max=y_max,
        n_used=int(keep_mask.sum()),
        n_dropped=int(window_mask.sum() - keep_mask.sum()),
    )


def fit_single_voigt_halpha(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    *,
    window_nm: tuple[float, float] = (600.0, 700.0),
    instrument_gauss_fwhm_nm: float = 0.13,
    intensity_threshold_rel: float = 0.05,
    center_initial_nm: float = 656.3,
    lorentz_initial_nm: float = 1.0,
    center_bounds_nm: tuple[float, float] = (650.0, 660.0),
    lorentz_bounds_nm: tuple[float, float] = (0.0, 10.0),
) -> dict[str, Any]:
    """Single-Voigt H-alpha fit, faithfully matching ``ElectronDensity.m``.

    Returns a dict with the fitted Lorentzian FWHM and center, their 95%
    confidence intervals (matching MATLAB's ``confint(f)``), the prepared
    data, the fit curve, residuals, and R^2.
    """

    prepared = _prepare_halpha_data(
        wavelength_nm, intensity, window_nm, intensity_threshold_rel
    )

    wg = float(instrument_gauss_fwhm_nm)

    def model(x: np.ndarray, wL: float, x0: float) -> np.ndarray:
        return voigt_unit_peak(x, x0, wL, wg)

    p0 = [float(lorentz_initial_nm), float(center_initial_nm)]
    lower = [float(lorentz_bounds_nm[0]), float(center_bounds_nm[0])]
    upper = [float(lorentz_bounds_nm[1]), float(center_bounds_nm[1])]
    popt, pcov = curve_fit(
        model,
        prepared.x_nm,
        prepared.I_norm,
        p0=p0,
        bounds=(lower, upper),
        maxfev=20_000,
    )
    wL_fit = float(popt[0])
    x0_fit = float(popt[1])
    y_fit = model(prepared.x_nm, wL_fit, x0_fit)

    perr = _stderr_from_covariance(pcov)
    ci_95 = _confidence_interval_95(popt, perr)

    metrics = _fit_metrics(prepared.I_norm, y_fit)

    return {
        "model": "single_voigt",
        "instrument_gauss_fwhm_nm": wg,
        "intensity_threshold_rel": float(intensity_threshold_rel),
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "n_points_used": prepared.n_used,
        "n_points_dropped": prepared.n_dropped,
        "raw_intensity_min": prepared.I_min,
        "raw_intensity_max": prepared.I_max,
        "parameters": {
            "lorentz_fwhm_nm": wL_fit,
            "center_nm": x0_fit,
        },
        "parameter_stderr": {
            "lorentz_fwhm_nm": float(perr[0]),
            "center_nm": float(perr[1]),
        },
        "confidence_interval_95": {
            "lorentz_fwhm_nm": [float(ci_95[0][0]), float(ci_95[0][1])],
            "center_nm": [float(ci_95[1][0]), float(ci_95[1][1])],
        },
        "fit_metrics": metrics,
        "data_curve": _xy_pairs(prepared.x_nm, prepared.I_norm),
        "fit_curve": _xy_pairs(prepared.x_nm, y_fit),
        "residual_curve": _xy_pairs(prepared.x_nm, prepared.I_norm - y_fit),
    }


def fit_two_voigt_halpha(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    *,
    window_nm: tuple[float, float] = (630.0, 680.0),
    instrument_gauss_fwhm_nm: float = 0.13,
    intensity_threshold_rel: float = 0.05,
    center_initial_nm: float = 656.28,
    lorentz1_initial_nm: float = 1.2,
    lorentz2_initial_nm: float = 0.3,
    weight_initial: float = 0.7,
    center_bounds_nm: tuple[float, float] = (650.0, 660.0),
    lorentz_bounds_nm: tuple[float, float] = (0.0, 10.0),
) -> dict[str, Any]:
    """Two-Voigt H-alpha fit, faithfully matching ``ElectronDensity_TwoVoigt.m``.

    Fits two Lorentzian populations sharing a center and Gaussian FWHM,
    weighted by ``a`` and ``1-a``. Returns parameters, 95% CIs, and the fit
    overlay.
    """

    prepared = _prepare_halpha_data(
        wavelength_nm, intensity, window_nm, intensity_threshold_rel
    )

    wg = float(instrument_gauss_fwhm_nm)

    def model(
        x: np.ndarray,
        wL1: float,
        wL2: float,
        a: float,
        x0: float,
    ) -> np.ndarray:
        return two_voigt_unit_peak(x, x0, wL1, wL2, wg, a)

    p0 = [
        float(lorentz1_initial_nm),
        float(lorentz2_initial_nm),
        float(weight_initial),
        float(center_initial_nm),
    ]
    lower = [
        float(lorentz_bounds_nm[0]),
        float(lorentz_bounds_nm[0]),
        0.0,
        float(center_bounds_nm[0]),
    ]
    upper = [
        float(lorentz_bounds_nm[1]),
        float(lorentz_bounds_nm[1]),
        1.0,
        float(center_bounds_nm[1]),
    ]
    popt, pcov = curve_fit(
        model,
        prepared.x_nm,
        prepared.I_norm,
        p0=p0,
        bounds=(lower, upper),
        maxfev=40_000,
    )
    wL1_fit, wL2_fit, a_fit, x0_fit = (float(v) for v in popt)
    y_fit = model(prepared.x_nm, wL1_fit, wL2_fit, a_fit, x0_fit)

    perr = _stderr_from_covariance(pcov)
    ci_95 = _confidence_interval_95(popt, perr)
    metrics = _fit_metrics(prepared.I_norm, y_fit)

    return {
        "model": "two_voigt",
        "instrument_gauss_fwhm_nm": wg,
        "intensity_threshold_rel": float(intensity_threshold_rel),
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "n_points_used": prepared.n_used,
        "n_points_dropped": prepared.n_dropped,
        "raw_intensity_min": prepared.I_min,
        "raw_intensity_max": prepared.I_max,
        "parameters": {
            "lorentz1_fwhm_nm": wL1_fit,
            "lorentz2_fwhm_nm": wL2_fit,
            "weight_pop1": a_fit,
            "weight_pop2": 1.0 - a_fit,
            "center_nm": x0_fit,
        },
        "parameter_stderr": {
            "lorentz1_fwhm_nm": float(perr[0]),
            "lorentz2_fwhm_nm": float(perr[1]),
            "weight_pop1": float(perr[2]),
            "center_nm": float(perr[3]),
        },
        "confidence_interval_95": {
            "lorentz1_fwhm_nm": [float(ci_95[0][0]), float(ci_95[0][1])],
            "lorentz2_fwhm_nm": [float(ci_95[1][0]), float(ci_95[1][1])],
            "weight_pop1": [float(ci_95[2][0]), float(ci_95[2][1])],
            "center_nm": [float(ci_95[3][0]), float(ci_95[3][1])],
        },
        "fit_metrics": metrics,
        "data_curve": _xy_pairs(prepared.x_nm, prepared.I_norm),
        "fit_curve": _xy_pairs(prepared.x_nm, y_fit),
        "residual_curve": _xy_pairs(prepared.x_nm, prepared.I_norm - y_fit),
    }


def _stderr_from_covariance(pcov: np.ndarray) -> np.ndarray:
    if pcov is None:
        return np.full(0, np.nan)
    diag = np.diag(np.asarray(pcov, dtype=float))
    return np.sqrt(np.where(diag > 0, diag, np.nan))


def _confidence_interval_95(popt: np.ndarray, perr: np.ndarray) -> list[tuple[float, float]]:
    """Match MATLAB ``confint(f)`` semantics: 95% CI = mean +/- 1.96 * stderr."""

    return [
        (float(popt[i] - 1.96 * perr[i]), float(popt[i] + 1.96 * perr[i]))
        for i in range(len(popt))
    ]


def _fit_metrics(y: np.ndarray, y_fit: np.ndarray) -> dict[str, float]:
    residual = y - y_fit
    rmse = float(np.sqrt(np.mean(residual**2)))
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "rmse": rmse,
        "r2": r2,
        "max_residual": float(np.max(np.abs(residual))),
    }


def _xy_pairs(x: np.ndarray, y: np.ndarray) -> list[dict[str, float]]:
    return [
        {"wavelength_nm": float(xi), "value": float(yi)}
        for xi, yi in zip(np.asarray(x), np.asarray(y), strict=True)
    ]
