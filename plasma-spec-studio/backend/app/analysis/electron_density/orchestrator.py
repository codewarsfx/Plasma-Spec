"""End-to-end electron-density diagnostic from a spectrum.

Glue between the Voigt fitters (``voigt_fits``) and the Stark-to-n_e
conversion (``stark_calibration``). The output is a single dict with the full
intermediate-value chain that the original spec asks for: measured FWHM,
instrumental FWHM, Lorentzian FWHM, vdW FWHM, Stark FWHM, n_e (cm^-3),
n_e uncertainty, fit quality, and the overlay/residual data for plotting.

Two models are supported, matching the lab MATLAB:

- ``single_voigt``: one Lorentzian width, used when the line shape looks like
  a single Voigt - the standard case.
- ``two_voigt``: two Lorentzian widths weighted by ``a``, for line-of-sight
  integrated spectra with two electron-density regions.

A line picker (``halpha`` / ``hbeta``) selects the Stark calibration. The
H-beta path is marked ``validated=False`` because it has not been calibrated
against the user's lab.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np

from app.analysis.electron_density.stark_calibration import (
    HALPHA_LAB,
    HBETA_CROSSCHECK,
    LineId,
    STARK_CALIBRATIONS,
    StarkCalibration,
    electron_density_cm3,
    two_population_electron_density,
)
from app.analysis.electron_density.voigt_fits import (
    fit_single_voigt_halpha,
    fit_two_voigt_halpha,
)
from app.core.line_shapes import gaussian_fwhm_from_sigma, voigt_fwhm, sigma_from_gaussian_fwhm
from app.core.spectrum import Spectrum


ModelChoice = Literal["single_voigt", "two_voigt"]


def compute_electron_density(
    spectrum: Spectrum,
    *,
    Tg_K: float,
    instrument_gauss_fwhm_nm: float = 0.13,
    line: LineId = "halpha",
    model: ModelChoice = "single_voigt",
    window_nm: tuple[float, float] | None = None,
    intensity_threshold_rel: float = 0.05,
    center_initial_nm: float | None = None,
    lorentz_initial_nm: float = 1.0,
    lorentz2_initial_nm: float = 0.3,
    weight_initial: float = 0.7,
    center_bounds_nm: tuple[float, float] | None = None,
    lorentz_bounds_nm: tuple[float, float] = (0.0, 10.0),
    Tg_uncertainty_K: float | None = None,
) -> dict[str, Any]:
    """Run the full Stark workflow on ``spectrum``.

    Parameters mirror the lab MATLAB defaults where applicable. The output
    dict reports every intermediate value the UI needs to display so users can
    trace n_e back through the fit.
    """

    if Tg_K <= 0:
        raise ValueError("Tg_K must be positive")
    if instrument_gauss_fwhm_nm <= 0:
        raise ValueError("instrument_gauss_fwhm_nm must be positive")
    if not 0 <= intensity_threshold_rel < 1:
        raise ValueError("intensity_threshold_rel must be in [0, 1)")
    if lorentz_initial_nm <= 0 or lorentz2_initial_nm <= 0:
        raise ValueError("initial Lorentzian FWHM values must be positive")
    if not 0 <= weight_initial <= 1:
        raise ValueError("weight_initial must be in [0, 1]")
    if lorentz_bounds_nm[0] < 0 or lorentz_bounds_nm[0] >= lorentz_bounds_nm[1]:
        raise ValueError("lorentz_bounds_nm must be ordered low < high with low >= 0")

    if line not in STARK_CALIBRATIONS:
        raise ValueError(f"unsupported line {line!r}; choose 'halpha' or 'hbeta'")
    calibration: StarkCalibration = STARK_CALIBRATIONS[line]

    # Defaults follow MATLAB:
    #   single_voigt: 600-700 nm, lorentz init 1.0, center init 656.3
    #   two_voigt:    630-680 nm, lorentz1 init 1.2, lorentz2 init 0.3, weight 0.7, center 656.28
    if center_initial_nm is None:
        center_initial_nm = calibration.wavelength_nm
    if center_bounds_nm is None:
        if line == "halpha":
            center_bounds_nm = (650.0, 660.0)
        else:  # hbeta
            center_bounds_nm = (483.0, 490.0)
    if window_nm is None:
        if model == "single_voigt":
            window_nm = (600.0, 700.0) if line == "halpha" else (482.0, 491.0)
        else:
            window_nm = (630.0, 680.0) if line == "halpha" else (483.0, 490.0)

    if model == "single_voigt":
        fit_result = fit_single_voigt_halpha(
            spectrum.wavelength_nm,
            spectrum.intensity,
            window_nm=window_nm,
            instrument_gauss_fwhm_nm=instrument_gauss_fwhm_nm,
            intensity_threshold_rel=intensity_threshold_rel,
            center_initial_nm=center_initial_nm,
            lorentz_initial_nm=lorentz_initial_nm,
            center_bounds_nm=center_bounds_nm,
            lorentz_bounds_nm=lorentz_bounds_nm,
        )
        wL = fit_result["parameters"]["lorentz_fwhm_nm"]
        wL_stderr = fit_result["parameter_stderr"]["lorentz_fwhm_nm"]
        wL_ci = fit_result["confidence_interval_95"]["lorentz_fwhm_nm"]

        ne_payload = electron_density_cm3(wL, Tg_K, calibration)
        ne_low = electron_density_cm3(wL_ci[0], Tg_K, calibration)["electron_density_cm3"]
        ne_high = electron_density_cm3(wL_ci[1], Tg_K, calibration)["electron_density_cm3"]
        electron_density: dict[str, Any] = dict(ne_payload)
        electron_density["confidence_interval_95"] = {
            "lower_cm3": ne_low,
            "upper_cm3": ne_high,
            "source": "Propagated from Lorentzian FWHM 95% CI only (matches lab MATLAB).",
        }

    elif model == "two_voigt":
        fit_result = fit_two_voigt_halpha(
            spectrum.wavelength_nm,
            spectrum.intensity,
            window_nm=window_nm,
            instrument_gauss_fwhm_nm=instrument_gauss_fwhm_nm,
            intensity_threshold_rel=intensity_threshold_rel,
            center_initial_nm=center_initial_nm,
            lorentz1_initial_nm=lorentz_initial_nm,
            lorentz2_initial_nm=lorentz2_initial_nm,
            weight_initial=weight_initial,
            center_bounds_nm=center_bounds_nm,
            lorentz_bounds_nm=lorentz_bounds_nm,
        )
        wL1 = fit_result["parameters"]["lorentz1_fwhm_nm"]
        wL2 = fit_result["parameters"]["lorentz2_fwhm_nm"]
        a = fit_result["parameters"]["weight_pop1"]
        wL1_ci = fit_result["confidence_interval_95"]["lorentz1_fwhm_nm"]

        electron_density = two_population_electron_density(wL1, wL2, a, Tg_K, calibration)
        # Match MATLAB: only wL1's CI is propagated (wL2_CI=0, a_CI=1 hardcoded).
        ne_low = two_population_electron_density(
            wL1_ci[0], wL2, a, Tg_K, calibration
        )["electron_density_cm3"]
        ne_high = two_population_electron_density(
            wL1_ci[1], wL2, a, Tg_K, calibration
        )["electron_density_cm3"]
        electron_density["confidence_interval_95"] = {
            "lower_cm3": ne_low,
            "upper_cm3": ne_high,
            "source": (
                "Propagated from wL1 95% CI only - matches MATLAB "
                "ElectronDensity_TwoVoigt.m which hard-codes wL2_CI=0, a_CI=1."
            ),
        }
    else:
        raise ValueError(f"unsupported model {model!r}")

    # Compose the response with all intermediate values traceable.
    warnings: list[str] = []
    if not calibration.validated:
        warnings.append(
            f"{calibration.line.upper()} calibration is a literature cross-check; "
            "not validated against the user's lab. Use H-alpha as primary."
        )
    if fit_result["fit_metrics"]["r2"] < 0.95:
        warnings.append(
            f"Voigt fit R^2 is {fit_result['fit_metrics']['r2']:.3f}; "
            "check the wavelength window, instrument FWHM, or baseline."
        )
    if instrument_gauss_fwhm_nm > 0.5:
        warnings.append(
            "Instrumental Gaussian FWHM > 0.5 nm is unusually large; double-check "
            "the spectrometer specification."
        )
    # If electron density couldn't be computed (Stark FWHM <= 0 in one or both
    # populations), surface that prominently and propagate any embedded warning
    # so the fit_quality classification reflects it.
    if isinstance(electron_density, dict):
        if electron_density.get("electron_density_cm3") is None:
            warnings.append(
                "Electron density is not computable: Stark FWHM <= 0 in at least one "
                "population (Lorentzian width is below the van der Waals contribution). "
                "Consider raising Tg, refitting on a different window, or using single-Voigt."
            )
        for embedded in (
            electron_density.get("warning"),
            (electron_density.get("population_1") or {}).get("warning"),
            (electron_density.get("population_2") or {}).get("warning"),
        ):
            if embedded and embedded not in warnings:
                warnings.append(embedded)

    # Aggregate measured FWHM = Voigt total width (Gaussian + Lorentzian).
    sigma = sigma_from_gaussian_fwhm(instrument_gauss_fwhm_nm)
    if model == "single_voigt":
        gamma = max(fit_result["parameters"]["lorentz_fwhm_nm"] / 2.0, 1e-12)
        total_fwhm = voigt_fwhm(sigma, gamma)
    else:
        gamma_eff = max(
            (fit_result["parameters"]["weight_pop1"] * fit_result["parameters"]["lorentz1_fwhm_nm"]
             + fit_result["parameters"]["weight_pop2"] * fit_result["parameters"]["lorentz2_fwhm_nm"]) / 2.0,
            1e-12,
        )
        total_fwhm = voigt_fwhm(sigma, gamma_eff)

    fwhm_breakdown = {
        "instrument_gauss_fwhm_nm": float(instrument_gauss_fwhm_nm),
        "lorentz_fwhm_nm": (
            float(fit_result["parameters"].get("lorentz_fwhm_nm"))
            if model == "single_voigt"
            else None
        ),
        "lorentz1_fwhm_nm": (
            float(fit_result["parameters"].get("lorentz1_fwhm_nm"))
            if model == "two_voigt"
            else None
        ),
        "lorentz2_fwhm_nm": (
            float(fit_result["parameters"].get("lorentz2_fwhm_nm"))
            if model == "two_voigt"
            else None
        ),
        "vdw_fwhm_nm": (
            float(electron_density.get("vdw_fwhm_nm"))
            if "vdw_fwhm_nm" in electron_density
            else float(electron_density.get("population_1", {}).get("vdw_fwhm_nm", 0.0))
        ),
        "stark_fwhm_nm": (
            float(electron_density.get("stark_fwhm_nm"))
            if "stark_fwhm_nm" in electron_density
            else float(electron_density.get("population_1", {}).get("stark_fwhm_nm", 0.0))
        ),
        "voigt_total_fwhm_nm": float(total_fwhm),
    }

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": "electron_density",
        "line": calibration.line,
        "model": model,
        "Tg_K": float(Tg_K),
        "Tg_uncertainty_K": float(Tg_uncertainty_K) if Tg_uncertainty_K is not None else None,
        "calibration_source": calibration.source,
        "calibration_validated": calibration.validated,
        "stark_constant_nm": calibration.stark_constant_nm,
        "vdw_prefactor_nm": calibration.vdw_prefactor_nm,
        "vdw_tg_exponent": calibration.vdw_tg_exponent,
        "voigt_fit": fit_result,
        "fwhm_breakdown_nm": fwhm_breakdown,
        "electron_density": electron_density,
        "warnings": warnings,
        "preprocessing_history": spectrum.preprocessing_history,
        "measured_curve": fit_result["data_curve"],
        "fit_curve": fit_result["fit_curve"],
        "residual_curve": fit_result["residual_curve"],
        "fit_quality": _classify_quality(fit_result["fit_metrics"], warnings),
        "metrics": fit_result["fit_metrics"],
        "parameters": {
            **fit_result["parameters"],
            "Tg_K": float(Tg_K),
            "electron_density_cm3": electron_density.get("electron_density_cm3"),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _classify_quality(metrics: dict[str, float], warnings: list[str]) -> str:
    r2 = metrics.get("r2", 0.0)
    if r2 < 0.85:
        return "bad"
    if warnings or r2 < 0.97:
        return "warning"
    return "good"
