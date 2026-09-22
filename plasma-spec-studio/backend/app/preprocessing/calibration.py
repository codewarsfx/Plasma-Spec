"""Wavelength calibration helpers."""

from __future__ import annotations

import numpy as np


def apply_wavelength_shift(wavelength_nm: np.ndarray, shift_nm: float) -> np.ndarray:
    """Apply a manual wavelength shift in nm."""

    return np.asarray(wavelength_nm, dtype=float) + float(shift_nm)


def apply_wavelength_calibration_pairs(
    wavelength_nm: np.ndarray,
    pairs: list[dict[str, float]] | list[list[float]] | list[tuple[float, float]],
    order: int = 1,
) -> np.ndarray:
    """Map measured wavelengths onto reference wavelengths using matched lines.

    ``pairs`` contains measured/reference wavelength pairs. A polynomial of
    degree ``order`` is fit as ``reference_nm = f(measured_nm)`` and then
    applied to the full wavelength axis.
    """

    degree = int(order)
    if degree < 1 or degree > 3:
        raise ValueError("wavelength calibration order must be between 1 and 3")

    measured: list[float] = []
    reference: list[float] = []
    for pair in pairs:
        if isinstance(pair, dict):
            measured_value = pair.get("measured_nm")
            reference_value = pair.get("reference_nm")
        else:
            if len(pair) != 2:
                raise ValueError("wavelength calibration pairs must contain measured and reference nm")
            measured_value, reference_value = pair
        measured_float = float(measured_value)
        reference_float = float(reference_value)
        if not np.isfinite(measured_float) or not np.isfinite(reference_float):
            raise ValueError("wavelength calibration pairs must be finite")
        measured.append(measured_float)
        reference.append(reference_float)

    if len(measured) < degree + 1:
        raise ValueError("not enough wavelength calibration pairs for requested order")
    if len(set(measured)) != len(measured):
        raise ValueError("wavelength calibration measured wavelengths must be unique")

    coefficients = np.polyfit(np.asarray(measured), np.asarray(reference), deg=degree)
    calibrated = np.polyval(coefficients, np.asarray(wavelength_nm, dtype=float))
    if np.any(np.diff(calibrated) <= 0):
        raise ValueError("wavelength calibration produced a non-monotonic wavelength axis")
    return calibrated
