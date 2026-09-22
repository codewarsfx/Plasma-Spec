"""H-beta line-shape fitting for Stark-broadening-oriented workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from scipy.optimize import curve_fit

from app.core.constants import H_BETA_CENTER_NM
from app.core.fitting_utils import (
    boundary_warnings,
    classify_fit_quality,
    crop_window,
    fit_metrics,
    serializable_array_pair,
)
from app.core.line_shapes import (
    gaussian,
    gaussian_fwhm_from_sigma,
    lorentzian,
    lorentzian_fwhm_from_gamma,
    voigt,
    voigt_fwhm,
)
from app.core.spectrum import Spectrum
from app.core.validation import saturation_warning


LineModel = Literal["gaussian", "lorentzian", "voigt"]


def fit_hbeta(
    spectrum: Spectrum,
    window_nm: tuple[float, float] | list[float] = (484.0, 488.0),
    model: LineModel = "voigt",
    center_bounds: tuple[float, float] | list[float] = (485.8, 486.4),
    sigma_bounds: tuple[float, float] | list[float] = (0.001, 1.0),
    gamma_bounds: tuple[float, float] | list[float] = (0.001, 1.0),
) -> dict[str, Any]:
    """Fit H-beta with Gaussian, Lorentzian, or Voigt profile plus linear baseline.

    The returned Lorentzian width is a line-shape parameter suitable for later
    Stark-broadening calibration, but this function intentionally does not
    convert it to electron density without a validated method.
    """

    x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    y = np.asarray(y, dtype=float)
    model = model.lower()  # type: ignore[assignment]
    if model not in ("gaussian", "lorentzian", "voigt"):
        raise ValueError("Hbeta model must be gaussian, lorentzian, or voigt")

    center0 = float(x[np.argmax(y)])
    center0 = float(np.clip(center0, center_bounds[0], center_bounds[1]))
    baseline0 = float(np.percentile(y, 10))
    amplitude0 = float(max(np.max(y) - baseline0, np.ptp(y), 1e-12) * max(np.ptp(x), 0.1))
    slope0 = 0.0
    x0 = float(np.mean(x))

    if model == "gaussian":
        p0 = [center0, amplitude0, 0.08, baseline0, slope0]
        lower = [center_bounds[0], 0.0, sigma_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, sigma_bounds[1], np.inf, np.inf]
        fit_func = lambda xx, center, amplitude, sigma, b0, b1: (
            b0 + b1 * (xx - x0) + amplitude * gaussian(xx, center, sigma)
        )
        names = ["center_nm", "amplitude", "sigma_nm", "baseline_0", "baseline_1"]
    elif model == "lorentzian":
        p0 = [center0, amplitude0, 0.04, baseline0, slope0]
        lower = [center_bounds[0], 0.0, gamma_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, gamma_bounds[1], np.inf, np.inf]
        fit_func = lambda xx, center, amplitude, gamma, b0, b1: (
            b0 + b1 * (xx - x0) + amplitude * lorentzian(xx, center, gamma)
        )
        names = ["center_nm", "amplitude", "gamma_nm", "baseline_0", "baseline_1"]
    else:
        p0 = [center0, amplitude0, 0.06, 0.03, baseline0, slope0]
        lower = [center_bounds[0], 0.0, sigma_bounds[0], gamma_bounds[0], -np.inf, -np.inf]
        upper = [center_bounds[1], np.inf, sigma_bounds[1], gamma_bounds[1], np.inf, np.inf]
        fit_func = lambda xx, center, amplitude, sigma, gamma, b0, b1: (
            b0 + b1 * (xx - x0) + amplitude * voigt(xx, center, sigma, gamma)
        )
        names = ["center_nm", "amplitude", "sigma_nm", "gamma_nm", "baseline_0", "baseline_1"]

    popt, pcov = curve_fit(
        fit_func,
        x,
        y,
        p0=p0,
        bounds=(lower, upper),
        maxfev=20_000,
    )
    y_fit = fit_func(x, *popt)
    residual = y - y_fit
    parameters = {name: float(value) for name, value in zip(names, popt, strict=True)}
    parameter_stderr = _parameter_stderr(names, pcov)

    if model == "gaussian":
        parameters["gaussian_fwhm_nm"] = gaussian_fwhm_from_sigma(parameters["sigma_nm"])
        parameters["lorentzian_fwhm_nm"] = None
        parameters["total_fwhm_nm"] = parameters["gaussian_fwhm_nm"]
        stark_fwhm = None
    elif model == "lorentzian":
        parameters["sigma_nm"] = None
        parameters["gaussian_fwhm_nm"] = None
        parameters["lorentzian_fwhm_nm"] = lorentzian_fwhm_from_gamma(parameters["gamma_nm"])
        parameters["total_fwhm_nm"] = parameters["lorentzian_fwhm_nm"]
        stark_fwhm = parameters["lorentzian_fwhm_nm"]
    else:
        parameters["gaussian_fwhm_nm"] = gaussian_fwhm_from_sigma(parameters["sigma_nm"])
        parameters["lorentzian_fwhm_nm"] = lorentzian_fwhm_from_gamma(parameters["gamma_nm"])
        parameters["total_fwhm_nm"] = voigt_fwhm(parameters["sigma_nm"], parameters["gamma_nm"])
        stark_fwhm = parameters["lorentzian_fwhm_nm"]

    metrics = fit_metrics(y, y_fit)
    warnings = _hbeta_warnings(parameters, metrics, x, y, model, center_bounds, sigma_bounds, gamma_bounds)
    density = estimate_electron_density_from_hbeta(stark_fwhm, method="placeholder")
    if density.get("warning"):
        warnings.append(density["warning"])

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": "hbeta_voigt" if model == "voigt" else f"hbeta_{model}",
        "model": model,
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "parameters": parameters,
        "parameter_stderr": parameter_stderr,
        "electron_density": density,
        "metrics": metrics,
        "fit_quality": classify_fit_quality(metrics, warnings),
        "warnings": warnings,
        "preprocessing_history": spectrum.preprocessing_history,
        "fit_curve": serializable_array_pair(x, y_fit),
        "measured_curve": serializable_array_pair(x, y),
        "residual_curve": serializable_array_pair(x, residual),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def estimate_electron_density_from_hbeta(
    stark_fwhm_nm: float | None,
    temperature_K: float | None = None,
    method: str = "placeholder",
) -> dict[str, Any]:
    """Estimate electron density from H-beta Stark width.

    The default placeholder intentionally does not report a density. Add lab- or
    literature-specific calibration methods here once a validated relation is
    selected for the instrument, plasma regime, and deconvolution convention.
    """

    if method == "placeholder":
        return {
            "electron_density_cm3": None,
            "method": method,
            "stark_fwhm_nm": stark_fwhm_nm,
            "temperature_K": temperature_K,
            "warning": (
                "Electron density conversion requires a validated Stark broadening "
                "calibration. The fitted Lorentzian/Stark width is reported, but "
                "density is not finalized."
            ),
        }
    raise ValueError(f"unsupported Hbeta electron density calibration method: {method}")


def _parameter_stderr(names: list[str], covariance: np.ndarray) -> dict[str, float | None]:
    if covariance is None or not np.all(np.isfinite(covariance)):
        return {name: None for name in names}
    diagonal = np.diag(covariance)
    return {
        name: (float(np.sqrt(value)) if value >= 0 and np.isfinite(value) else None)
        for name, value in zip(names, diagonal, strict=True)
    }


def _hbeta_warnings(
    parameters: dict[str, Any],
    metrics: dict[str, float],
    x: np.ndarray,
    y: np.ndarray,
    model: LineModel,
    center_bounds: tuple[float, float] | list[float],
    sigma_bounds: tuple[float, float] | list[float],
    gamma_bounds: tuple[float, float] | list[float],
) -> list[str]:
    warnings: list[str] = []
    if metrics["snr"] < 5:
        warnings.append("Weak signal or low SNR")
    if metrics["normalized_rmse"] > 0.12:
        warnings.append("High residual error")
    if abs(parameters["center_nm"] - H_BETA_CENTER_NM) > 0.25:
        warnings.append("Large wavelength shift relative to Hbeta nominal center")
    saturation = saturation_warning(y)
    if saturation:
        warnings.append(saturation)
    bounds: dict[str, tuple[float, float]] = {"center_nm": (float(center_bounds[0]), float(center_bounds[1]))}
    if model in ("gaussian", "voigt") and parameters.get("sigma_nm") is not None:
        bounds["sigma_nm"] = (float(sigma_bounds[0]), float(sigma_bounds[1]))
    if model in ("lorentzian", "voigt") and parameters.get("gamma_nm") is not None:
        bounds["gamma_nm"] = (float(gamma_bounds[0]), float(gamma_bounds[1]))
    warnings.extend(boundary_warnings(parameters, bounds))
    if parameters.get("total_fwhm_nm") and parameters["total_fwhm_nm"] > np.ptp(x) * 0.75:
        warnings.append("Line width is large relative to fitting window")
    return warnings

