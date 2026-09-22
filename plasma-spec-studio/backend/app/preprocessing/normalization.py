"""Spectrum normalization utilities."""

from __future__ import annotations

import numpy as np

from app.core.fitting_utils import crop_window


def normalize(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    method: str = "max",
    window_nm: tuple[float, float] | list[float] | None = None,
) -> np.ndarray:
    """Normalize intensity by max, area, or selected window."""

    y = np.asarray(intensity, dtype=float)
    if method in ("none", "No normalization", None):
        return y.copy()
    if method == "max":
        scale = np.max(np.abs(y))
    elif method == "area":
        scale = abs(float(np.trapezoid(y, wavelength_nm)))
    elif method == "window":
        if window_nm is None:
            raise ValueError("window normalization requires window_nm")
        wx, wy = crop_window(wavelength_nm, y, window_nm)
        scale = np.max(np.abs(wy))
        if scale == 0:
            scale = abs(float(np.trapezoid(wy, wx)))
    else:
        raise ValueError(f"unsupported normalization method: {method}")
    if scale == 0 or not np.isfinite(scale):
        raise ValueError("normalization scale is zero or not finite")
    return y / scale
