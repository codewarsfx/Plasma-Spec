"""Convolution helpers for synthetic spectra."""

from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve


def convolve_same(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolve ``signal`` with ``kernel`` and return an array of equal length."""

    signal = np.asarray(signal, dtype=float)
    kernel = np.asarray(kernel, dtype=float)
    if kernel.ndim != 1 or signal.ndim != 1:
        raise ValueError("signal and kernel must be one-dimensional")
    area = np.trapezoid(kernel)
    if area != 0:
        kernel = kernel / area
    return fftconvolve(signal, kernel, mode="same")
