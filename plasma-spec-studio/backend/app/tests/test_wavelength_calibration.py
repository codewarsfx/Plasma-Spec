"""Wavelength calibration preprocessing tests."""

from __future__ import annotations

import numpy as np

from app.core.spectrum import Spectrum
from app.preprocessing.pipeline import apply_preprocessing_operations


def test_wavelength_calibration_pairs_apply_linear_mapping():
    measured = np.linspace(300.0, 400.0, 11)
    reference = measured + 0.25 + 0.001 * (measured - 350.0)
    spectrum = Spectrum("cal.csv", measured, np.ones_like(measured))

    calibrated = apply_preprocessing_operations(
        spectrum,
        [
            {
                "operation": "wavelength_calibration",
                "params": {
                    "order": 1,
                    "pairs": [
                        {"measured_nm": float(measured[0]), "reference_nm": float(reference[0])},
                        {"measured_nm": float(measured[-1]), "reference_nm": float(reference[-1])},
                    ],
                },
            }
        ],
    )

    assert np.allclose(calibrated.wavelength_nm, reference)
    assert calibrated.preprocessing_history[-1]["operation"] == "wavelength_calibration"
