from __future__ import annotations

import numpy as np

from app.core.line_shapes import (
    gaussian,
    gaussian_fwhm_from_sigma,
    lorentzian,
    lorentzian_fwhm_from_gamma,
    sigma_from_gaussian_fwhm,
    voigt,
    voigt_fwhm,
)


def test_gaussian_is_unit_area_and_peaked_at_center():
    x = np.linspace(-5, 5, 10_001)
    profile = gaussian(x, center=0, sigma=0.4)

    assert np.isclose(np.trapezoid(profile, x), 1.0, atol=1e-5)
    assert x[np.argmax(profile)] == 0


def test_lorentzian_shape_and_fwhm():
    x = np.linspace(-100, 100, 200_001)
    profile = lorentzian(x, center=0, gamma=0.2)

    assert np.isclose(np.trapezoid(profile, x), 1.0, atol=2e-3)
    assert np.isclose(lorentzian_fwhm_from_gamma(0.2), 0.4)


def test_voigt_shape_and_fwhm_is_positive():
    x = np.linspace(-10, 10, 20_001)
    sigma = sigma_from_gaussian_fwhm(0.2)
    profile = voigt(x, center=0, sigma=sigma, gamma=0.04)

    assert np.isclose(np.trapezoid(profile, x), 1.0, atol=3e-3)
    assert voigt_fwhm(sigma, 0.04) > gaussian_fwhm_from_sigma(sigma)
