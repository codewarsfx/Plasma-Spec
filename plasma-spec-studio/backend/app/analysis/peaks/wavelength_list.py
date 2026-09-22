"""Wavelength-list peak analysis workflow.

A user (or a recipe) gives a list of peaks of interest. For each peak we crop
the spectrum to a small window centered on the requested wavelength, subtract
a local linear baseline computed from the window edges, and report:

- the peak location and intensity in raw and baseline-subtracted data
- the integrated and baseline-subtracted area over the window
- the data-derived FWHM (linear interpolation across the half-max level)
- the local SNR

Optionally, the peak can be fit with a Gaussian, Lorentzian, or Voigt profile
on top of a linear baseline. The fit result returns the fitted center,
amplitude, line-shape widths, FWHM, area under the fitted profile, R^2, and a
converged flag. Warnings flag low SNR, peaks that drifted to the window edge,
poor R^2, and fitted centers that are far from the requested center.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from scipy.optimize import curve_fit

from app.core.fitting_utils import classify_fit_quality, crop_window, estimate_snr, fit_metrics
from app.core.line_shapes import (
    gaussian,
    gaussian_fwhm_from_sigma,
    lorentzian,
    lorentzian_fwhm_from_gamma,
    voigt,
    voigt_fwhm,
)
from app.core.spectrum import Spectrum


FitModel = Literal["gaussian", "lorentzian", "voigt"]
DEFAULT_HALF_WIDTH_NM = 0.5
FAR_FROM_REQUESTED_FRACTION = 0.5  # fraction of half-width before we warn


def analyze_peak_list(
    spectrum: Spectrum,
    peaks: list[dict[str, Any]],
    default_half_width_nm: float = DEFAULT_HALF_WIDTH_NM,
    default_fit_model: FitModel | None = None,
) -> dict[str, Any]:
    """Analyze each requested peak and return a unified result dict.

    Each entry in ``peaks`` may be a dict containing:

    - ``label``: free-text identifier
    - ``center_nm``: requested peak center (required)
    - ``half_width_nm``: half-width of the search/integration window
    - ``fit_model``: one of "gaussian", "lorentzian", "voigt", or None
    - ``species`` / ``transition``: optional bookkeeping fields preserved on
      the output for joinable downstream tables
    """

    results: list[dict[str, Any]] = []
    for entry in peaks:
        center_nm = float(entry["center_nm"])
        half_width_nm = float(entry.get("half_width_nm", default_half_width_nm))
        label = str(entry.get("label", f"peak_{center_nm:.2f}"))
        fit_model = entry.get("fit_model", default_fit_model)
        if fit_model is not None and fit_model not in ("gaussian", "lorentzian", "voigt"):
            raise ValueError(
                f"unsupported fit_model {fit_model!r}; choose gaussian, lorentzian, or voigt"
            )
        result = _analyze_single_peak(
            spectrum=spectrum,
            label=label,
            requested_center_nm=center_nm,
            half_width_nm=half_width_nm,
            fit_model=fit_model,
            extra_fields={
                key: entry[key]
                for key in ("species", "transition", "notes")
                if key in entry
            },
        )
        results.append(result)

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": "peak_list",
        "preprocessing_history": spectrum.preprocessing_history,
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _analyze_single_peak(
    spectrum: Spectrum,
    label: str,
    requested_center_nm: float,
    half_width_nm: float,
    fit_model: FitModel | None,
    extra_fields: dict[str, Any],
) -> dict[str, Any]:
    window = (requested_center_nm - half_width_nm, requested_center_nm + half_width_nm)
    warnings: list[str] = []
    try:
        x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window)
    except ValueError as exc:
        return {
            "label": label,
            "requested_center_nm": float(requested_center_nm),
            "search_half_width_nm": float(half_width_nm),
            "window_nm": [float(window[0]), float(window[1])],
            "fit_model": fit_model,
            "data": None,
            "fit": None,
            "fit_quality": "bad",
            "warnings": [f"could not crop window: {exc}"],
            **extra_fields,
        }

    baseline = _linear_edge_baseline(x, y)
    corrected = y - baseline
    snr = float(estimate_snr(corrected))
    if snr < 3:
        warnings.append("Low SNR for this peak")

    peak_idx_raw = int(np.argmax(y))
    peak_idx_corr = int(np.argmax(corrected))
    peak_wavelength_nm = float(x[peak_idx_corr])

    edge_threshold = max(half_width_nm * 0.05, (x[-1] - x[0]) * 0.05)
    if (
        abs(peak_wavelength_nm - x[0]) <= edge_threshold
        or abs(peak_wavelength_nm - x[-1]) <= edge_threshold
    ):
        warnings.append("Peak is at the search window edge; widen the window")

    fwhm_data_nm = _fwhm_from_data(x, corrected)
    integrated_area = float(np.trapezoid(y, x))
    baseline_subtracted_area = float(np.trapezoid(corrected, x))

    data_section: dict[str, Any] = {
        "peak_wavelength_nm": peak_wavelength_nm,
        "peak_height_raw": float(y[peak_idx_raw]),
        "peak_height_baseline_subtracted": float(corrected[peak_idx_corr]),
        "integrated_area": integrated_area,
        "baseline_subtracted_area": baseline_subtracted_area,
        "fwhm_data_nm": fwhm_data_nm,
        "snr": snr,
        "n_points": int(len(x)),
        "local_baseline_left": float(baseline[0]),
        "local_baseline_right": float(baseline[-1]),
    }

    fit_section: dict[str, Any] | None = None
    if fit_model is not None:
        fit_section = _fit_profile(
            x=x,
            y=y,
            requested_center_nm=requested_center_nm,
            half_width_nm=half_width_nm,
            model=fit_model,
            warnings=warnings,
        )

    if fit_section is not None and fit_section.get("converged"):
        center_fit = fit_section["center_nm"]
        if abs(center_fit - requested_center_nm) > half_width_nm * FAR_FROM_REQUESTED_FRACTION:
            warnings.append("Fitted center is far from the requested wavelength")

    if fit_section is not None:
        # Fit available: classify on SNR and normalized RMSE the same way the
        # rest of the codebase does.
        metrics_for_classification: dict[str, float] = {
            "snr": snr,
            "normalized_rmse": float(fit_section.get("normalized_rmse", 0.0) or 0.0),
            "r2": float(fit_section.get("r2", 0.0) or 0.0),
        }
        fit_quality = classify_fit_quality(metrics_for_classification, warnings)
    else:
        # Data-only path: only the SNR is meaningful, plus any warnings.
        if snr < 3:
            fit_quality = "bad"
        elif snr < 8 or warnings:
            fit_quality = "warning"
        else:
            fit_quality = "good"

    return {
        "label": label,
        "requested_center_nm": float(requested_center_nm),
        "search_half_width_nm": float(half_width_nm),
        "window_nm": [float(window[0]), float(window[1])],
        "fit_model": fit_model,
        "data": data_section,
        "fit": fit_section,
        "fit_quality": fit_quality,
        "warnings": warnings,
        **extra_fields,
    }


def _linear_edge_baseline(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Linear baseline from the median of the leftmost / rightmost edge bins."""

    edge_count = max(2, len(x) // 10)
    left = float(np.median(y[:edge_count]))
    right = float(np.median(y[-edge_count:]))
    return np.interp(x, [x[0], x[-1]], [left, right])


def _fwhm_from_data(x: np.ndarray, y: np.ndarray) -> float | None:
    """Estimate FWHM by linear interpolation around the half-maximum level."""

    if len(y) < 5:
        return None
    peak = float(np.max(y))
    if peak <= 0:
        return None
    half = peak / 2.0
    indices = np.where(y >= half)[0]
    if len(indices) < 2:
        return None
    left_idx = int(indices[0])
    right_idx = int(indices[-1])

    def _interp(side_idx: int, neighbor_idx: int) -> float:
        y_side = y[side_idx]
        y_neighbor = y[neighbor_idx]
        if y_side == y_neighbor:
            return float(x[side_idx])
        fraction = (half - y_neighbor) / (y_side - y_neighbor)
        return float(x[neighbor_idx] + fraction * (x[side_idx] - x[neighbor_idx]))

    left_x = _interp(left_idx, max(left_idx - 1, 0))
    right_x = _interp(right_idx, min(right_idx + 1, len(x) - 1))
    fwhm = right_x - left_x
    return float(fwhm) if fwhm > 0 else None


def _fit_profile(
    x: np.ndarray,
    y: np.ndarray,
    requested_center_nm: float,
    half_width_nm: float,
    model: FitModel,
    warnings: list[str],
) -> dict[str, Any]:
    x0 = float(np.mean(x))
    baseline0 = float(np.percentile(y, 10))
    amplitude0 = float(max(np.max(y) - baseline0, np.ptp(y), 1e-12) * max(np.ptp(x), 0.1))
    center_bounds = (
        float(requested_center_nm - half_width_nm),
        float(requested_center_nm + half_width_nm),
    )
    width_bounds = (1e-4, max(half_width_nm * 2.0, 0.5))

    if model == "gaussian":
        names = ["center_nm", "amplitude", "sigma_nm", "baseline_0", "baseline_1"]
        p0 = [requested_center_nm, amplitude0, max(half_width_nm * 0.3, 1e-3), baseline0, 0.0]
        lower = [center_bounds[0], 0.0, width_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, width_bounds[1], np.inf, np.inf]

        def fit_func(xx, center, amplitude, sigma, b0, b1):
            return b0 + b1 * (xx - x0) + amplitude * gaussian(xx, center, sigma)

    elif model == "lorentzian":
        names = ["center_nm", "amplitude", "gamma_nm", "baseline_0", "baseline_1"]
        p0 = [requested_center_nm, amplitude0, max(half_width_nm * 0.2, 1e-3), baseline0, 0.0]
        lower = [center_bounds[0], 0.0, width_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, width_bounds[1], np.inf, np.inf]

        def fit_func(xx, center, amplitude, gamma, b0, b1):
            return b0 + b1 * (xx - x0) + amplitude * lorentzian(xx, center, gamma)

    else:  # voigt
        names = ["center_nm", "amplitude", "sigma_nm", "gamma_nm", "baseline_0", "baseline_1"]
        p0 = [
            requested_center_nm,
            amplitude0,
            max(half_width_nm * 0.2, 1e-3),
            max(half_width_nm * 0.15, 1e-3),
            baseline0,
            0.0,
        ]
        lower = [center_bounds[0], 0.0, width_bounds[0], width_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, width_bounds[1], width_bounds[1], np.inf, np.inf]

        def fit_func(xx, center, amplitude, sigma, gamma, b0, b1):
            return b0 + b1 * (xx - x0) + amplitude * voigt(xx, center, sigma, gamma)

    try:
        popt, pcov = curve_fit(fit_func, x, y, p0=p0, bounds=(lower, upper), maxfev=20_000)
    except Exception as exc:  # pragma: no cover - SciPy raises a variety of errors
        warnings.append(f"Profile fit did not converge: {exc}")
        return {"model": model, "converged": False, "error": str(exc)}

    y_fit = fit_func(x, *popt)
    metrics = fit_metrics(y, y_fit)
    parameters = {name: float(value) for name, value in zip(names, popt, strict=True)}
    parameter_stderr = _parameter_stderr(names, pcov)

    if model == "gaussian":
        parameters["gaussian_fwhm_nm"] = gaussian_fwhm_from_sigma(parameters["sigma_nm"])
        parameters["fwhm_nm"] = parameters["gaussian_fwhm_nm"]
    elif model == "lorentzian":
        parameters["lorentzian_fwhm_nm"] = lorentzian_fwhm_from_gamma(parameters["gamma_nm"])
        parameters["fwhm_nm"] = parameters["lorentzian_fwhm_nm"]
    else:
        parameters["gaussian_fwhm_nm"] = gaussian_fwhm_from_sigma(parameters["sigma_nm"])
        parameters["lorentzian_fwhm_nm"] = lorentzian_fwhm_from_gamma(parameters["gamma_nm"])
        parameters["fwhm_nm"] = voigt_fwhm(parameters["sigma_nm"], parameters["gamma_nm"])

    # Closed-form profile area under the line minus baseline is just the
    # amplitude (the line-shape functions are unit-area). Numerical integration
    # of the baseline-subtracted fit gives the same value to round-off and is
    # robust to future shape changes.
    fit_minus_baseline = y_fit - (parameters["baseline_0"] + parameters["baseline_1"] * (x - x0))
    fit_area = float(np.trapezoid(fit_minus_baseline, x))

    return {
        "model": model,
        "converged": True,
        **parameters,
        "parameter_stderr": parameter_stderr,
        "fit_area": fit_area,
        "r2": metrics["r2"],
        "rmse": metrics["rmse"],
        "normalized_rmse": metrics["normalized_rmse"],
        "max_residual": metrics["max_residual"],
    }


def _parameter_stderr(names: list[str], covariance: np.ndarray) -> dict[str, float | None]:
    if covariance is None or not np.all(np.isfinite(covariance)):
        return {name: None for name in names}
    diagonal = np.diag(covariance)
    return {
        name: (float(np.sqrt(value)) if value >= 0 and np.isfinite(value) else None)
        for name, value in zip(names, diagonal, strict=True)
    }
