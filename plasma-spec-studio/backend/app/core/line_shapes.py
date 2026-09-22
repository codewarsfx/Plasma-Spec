"""Normalized line-shape functions and broadening helpers."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from scipy.special import wofz


SQRT_2PI = math.sqrt(2.0 * math.pi)


def gaussian(x: np.ndarray, center: float, sigma: float) -> np.ndarray:
    """Return a unit-area Gaussian profile.

    Parameters
    ----------
    x:
        Wavelength grid in nm.
    center:
        Center wavelength in nm.
    sigma:
        Standard deviation in nm. Must be positive.
    """

    x = np.asarray(x, dtype=float)
    sigma = _positive_width(sigma, "sigma")
    return np.exp(-0.5 * ((x - center) / sigma) ** 2) / (sigma * SQRT_2PI)


def lorentzian(x: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Return a unit-area Lorentzian profile.

    ``gamma`` is the half width at half maximum in nm.
    """

    x = np.asarray(x, dtype=float)
    gamma = _positive_width(gamma, "gamma")
    return (gamma / math.pi) / ((x - center) ** 2 + gamma**2)


def voigt(x: np.ndarray, center: float, sigma: float, gamma: float) -> np.ndarray:
    """Return a unit-area Voigt profile using ``scipy.special.wofz``.

    ``sigma`` is the Gaussian standard deviation in nm and ``gamma`` is the
    Lorentzian half width at half maximum in nm.
    """

    x = np.asarray(x, dtype=float)
    sigma = _positive_width(sigma, "sigma")
    gamma = _positive_width(gamma, "gamma")
    z = ((x - center) + 1j * gamma) / (sigma * math.sqrt(2.0))
    return np.real(wofz(z)) / (sigma * SQRT_2PI)


def gaussian_fwhm_from_sigma(sigma: float) -> float:
    """Convert Gaussian sigma to FWHM."""

    return 2.0 * math.sqrt(2.0 * math.log(2.0)) * _positive_width(sigma, "sigma")


def sigma_from_gaussian_fwhm(fwhm: float) -> float:
    """Convert Gaussian FWHM to sigma."""

    return _positive_width(fwhm, "fwhm") / (2.0 * math.sqrt(2.0 * math.log(2.0)))


def lorentzian_fwhm_from_gamma(gamma: float) -> float:
    """Convert Lorentzian HWHM gamma to FWHM."""

    return 2.0 * _positive_width(gamma, "gamma")


def gamma_from_lorentzian_fwhm(fwhm: float) -> float:
    """Convert Lorentzian FWHM to HWHM gamma."""

    return _positive_width(fwhm, "fwhm") / 2.0


def voigt_fwhm(sigma: float, gamma: float) -> float:
    """Approximate Voigt FWHM using the Olivero-Longbothum formula."""

    gaussian_fwhm = gaussian_fwhm_from_sigma(sigma)
    lorentz_fwhm = lorentzian_fwhm_from_gamma(gamma)
    return 0.5346 * lorentz_fwhm + math.sqrt(
        0.2166 * lorentz_fwhm**2 + gaussian_fwhm**2
    )


def instrument_profile(
    x: np.ndarray,
    center: float,
    kind: Literal["gaussian", "lorentzian", "voigt"] = "gaussian",
    gaussian_fwhm_nm: float = 0.1,
    lorentzian_fwhm_nm: float = 0.02,
) -> np.ndarray:
    """Build a normalized instrumental profile on ``x``.

    This helper keeps instrumental broadening explicit and swappable. More
    instrument-specific response functions can be added behind the same API.
    """

    if kind == "gaussian":
        return gaussian(x, center, sigma_from_gaussian_fwhm(gaussian_fwhm_nm))
    if kind == "lorentzian":
        return lorentzian(x, center, gamma_from_lorentzian_fwhm(lorentzian_fwhm_nm))
    if kind == "voigt":
        return voigt(
            x,
            center,
            sigma_from_gaussian_fwhm(gaussian_fwhm_nm),
            gamma_from_lorentzian_fwhm(lorentzian_fwhm_nm),
        )
    raise ValueError(f"Unsupported instrumental profile kind: {kind}")


def _positive_width(value: float, name: str) -> float:
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite width")
    return value

