"""Optional smoothing filters."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def moving_average(intensity: np.ndarray, window_points: int = 5) -> np.ndarray:
    """Apply a centered moving average filter."""

    y = np.asarray(intensity, dtype=float)
    window_points = int(window_points)
    if window_points <= 1:
        return y.copy()
    if window_points > len(y):
        raise ValueError("moving average window is larger than spectrum")
    kernel = np.ones(window_points) / window_points
    return np.convolve(y, kernel, mode="same")


def savitzky_golay(
    intensity: np.ndarray, window_points: int = 9, polyorder: int = 2
) -> np.ndarray:
    """Apply a Savitzky-Golay filter.

    Smoothing can distort narrow spectral line shapes; the UI surfaces this as a
    scientific warning before users apply it to fitting recipes.
    """

    y = np.asarray(intensity, dtype=float)
    window_points = int(window_points)
    if window_points % 2 == 0:
        window_points += 1
    if window_points <= polyorder:
        raise ValueError("Savitzky-Golay window must be larger than polyorder")
    if window_points > len(y):
        raise ValueError("Savitzky-Golay window is larger than spectrum")
    return savgol_filter(y, window_points, int(polyorder))

