"""Cosmic spike removal helpers."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter


def remove_spikes(
    intensity: np.ndarray, window_points: int = 5, threshold_sigma: float = 6.0
) -> tuple[np.ndarray, np.ndarray]:
    """Replace isolated spikes using median-filter thresholding.

    Returns the cleaned signal and a boolean mask of replaced points.
    """

    y = np.asarray(intensity, dtype=float)
    window_points = max(3, int(window_points))
    if window_points % 2 == 0:
        window_points += 1
    median = median_filter(y, size=window_points, mode="nearest")
    residual = y - median
    robust_sigma = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    if robust_sigma <= 0:
        return y.copy(), np.zeros_like(y, dtype=bool)
    mask = residual > threshold_sigma * robust_sigma
    cleaned = y.copy()
    cleaned[mask] = median[mask]
    return cleaned, mask

