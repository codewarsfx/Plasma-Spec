"""Baseline correction algorithms for OES spectra."""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.interpolate import interp1d
from scipy.sparse.linalg import spsolve


def polynomial_baseline(
    wavelength_nm: np.ndarray, intensity: np.ndarray, order: int = 2
) -> tuple[np.ndarray, np.ndarray]:
    """Subtract a polynomial baseline from the spectrum."""

    x = np.asarray(wavelength_nm, dtype=float)
    y = np.asarray(intensity, dtype=float)
    order = int(order)
    if order < 0 or order >= len(x):
        raise ValueError("polynomial order must be >= 0 and smaller than number of points")
    coefficients = np.polyfit(x - np.mean(x), y, order)
    baseline = np.polyval(coefficients, x - np.mean(x))
    return y - baseline, baseline


def asymmetric_least_squares_baseline(
    intensity: np.ndarray, lam: float = 100_000.0, p: float = 0.01, n_iter: int = 10
) -> np.ndarray:
    """Estimate baseline using asymmetric least squares smoothing.

    The algorithm follows the common Eilers-Boelens ALS approach. ``lam``
    controls smoothness and ``p`` controls asymmetry.
    """

    y = np.asarray(intensity, dtype=float)
    if len(y) < 3:
        raise ValueError("ALS baseline requires at least three points")
    if lam <= 0:
        raise ValueError("lambda/smoothness must be positive")
    if not 0 < p < 1:
        raise ValueError("p/asymmetry must be between 0 and 1")
    difference = sparse.diags(
        [1.0, -2.0, 1.0], [0, -1, -2], shape=(len(y), len(y) - 2), dtype=float
    )
    weights = np.ones(len(y))
    for _ in range(int(n_iter)):
        weight_matrix = sparse.spdiags(weights, 0, len(y), len(y))
        system = (weight_matrix + lam * difference @ difference.T).tocsc()
        baseline = spsolve(system, weights * y)
        weights = p * (y > baseline) + (1.0 - p) * (y < baseline)
    return np.asarray(baseline)


def baseline_als_corrected(
    intensity: np.ndarray, lam: float = 100_000.0, p: float = 0.01, n_iter: int = 10
) -> tuple[np.ndarray, np.ndarray]:
    """Return ALS baseline-corrected signal and baseline."""

    baseline = asymmetric_least_squares_baseline(intensity, lam=lam, p=p, n_iter=n_iter)
    return np.asarray(intensity, dtype=float) - baseline, baseline


def manual_anchor_baseline(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    anchors: list[tuple[float, float]] | list[dict[str, float]],
) -> tuple[np.ndarray, np.ndarray]:
    """Subtract a baseline interpolated from user-selected anchor points."""

    if len(anchors) < 2:
        raise ValueError("manual baseline requires at least two anchor points")
    x = np.asarray(wavelength_nm, dtype=float)
    y = np.asarray(intensity, dtype=float)
    anchor_x: list[float] = []
    anchor_y: list[float] = []
    for anchor in anchors:
        if isinstance(anchor, dict):
            anchor_x.append(float(anchor["wavelength_nm"]))
            anchor_y.append(float(anchor["intensity"]))
        else:
            anchor_x.append(float(anchor[0]))
            anchor_y.append(float(anchor[1]))
    interpolator = interp1d(
        anchor_x,
        anchor_y,
        kind="linear",
        bounds_error=False,
        fill_value=(anchor_y[0], anchor_y[-1]),
    )
    baseline = interpolator(x)
    return y - baseline, baseline
