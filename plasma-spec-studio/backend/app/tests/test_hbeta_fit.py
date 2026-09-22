from __future__ import annotations

import numpy as np

from app.core.line_shapes import voigt
from app.core.spectrum import Spectrum
from app.models.hbeta_voigt_model import fit_hbeta


def test_hbeta_voigt_recovers_synthetic_parameters():
    rng = np.random.default_rng(4)
    x = np.linspace(484, 488, 401)
    center = 486.13
    sigma = 0.055
    gamma = 0.04
    amplitude = 120.0
    baseline = 12.0 + 0.4 * (x - x.mean())
    y = baseline + amplitude * voigt(x, center=center, sigma=sigma, gamma=gamma)
    y = y + rng.normal(0, 0.08, size=len(x))
    spectrum = Spectrum("synthetic_hbeta.csv", x, y)

    result = fit_hbeta(spectrum, model="voigt")
    params = result["parameters"]

    assert abs(params["center_nm"] - center) < 0.01
    assert abs(params["sigma_nm"] - sigma) < 0.02
    assert abs(params["gamma_nm"] - gamma) < 0.02
    assert params["total_fwhm_nm"] > 0
    assert result["electron_density"]["electron_density_cm3"] is None
    assert any("validated Stark" in warning for warning in result["warnings"])

