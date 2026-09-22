from __future__ import annotations

import numpy as np

from app.core.spectrum import Spectrum
from app.preprocessing.baseline import baseline_als_corrected, polynomial_baseline
from app.preprocessing.normalization import normalize
from app.preprocessing.pipeline import apply_preprocessing_operations


def test_baseline_correction_returns_same_length():
    x = np.linspace(300, 320, 200)
    y = 0.2 * x + np.exp(-0.5 * ((x - 310) / 0.4) ** 2)

    corrected_poly, baseline_poly = polynomial_baseline(x, y, order=1)
    corrected_als, baseline_als = baseline_als_corrected(y, lam=10_000, p=0.01)

    assert len(corrected_poly) == len(y)
    assert len(baseline_poly) == len(y)
    assert len(corrected_als) == len(y)
    assert len(baseline_als) == len(y)


def test_normalization_and_crop_pipeline():
    spectrum = Spectrum("demo.csv", np.linspace(480, 490, 101), np.linspace(0, 100, 101))

    processed = apply_preprocessing_operations(
        spectrum,
        [
            {"operation": "crop", "params": {"window_nm": [484, 488]}},
            {"operation": "normalize", "params": {"method": "max"}},
        ],
    )

    assert processed.wavelength_nm.min() >= 484
    assert processed.wavelength_nm.max() <= 488
    assert np.isclose(processed.intensity.max(), 1.0)
    assert [item["operation"] for item in processed.preprocessing_history] == ["crop", "normalize"]


def test_background_subtraction_interpolates():
    spectrum = Spectrum("signal.csv", np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0]))
    background = Spectrum("dark.csv", np.array([1.0, 3.0]), np.array([1.0, 3.0]))

    processed = apply_preprocessing_operations(
        spectrum,
        [{"operation": "background_subtract", "params": {}}],
        background=background,
    )

    assert np.allclose(processed.intensity, [9.0, 18.0, 27.0])


def test_area_normalization():
    x = np.linspace(0, 1, 100)
    y = np.ones_like(x) * 2

    normalized = normalize(x, y, method="area")

    assert np.isclose(np.trapezoid(normalized, x), 1.0)
