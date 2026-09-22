from __future__ import annotations

import numpy as np

from app.core.spectrum import Spectrum
from app.models.peak_area_model import analyze_peak_window


def test_peak_area_integrates_known_peak():
    x = np.linspace(0, 10, 1001)
    y = np.maximum(0, 1 - np.abs(x - 5))
    spectrum = Spectrum("triangle.csv", x, y)

    result = analyze_peak_window(spectrum, [4, 6], name="triangle")

    assert np.isclose(result["parameters"]["integrated_area"], 1.0, atol=0.01)
    assert np.isclose(result["parameters"]["max_wavelength_nm"], 5.0)
    assert result["parameters"]["snr"] > 1

