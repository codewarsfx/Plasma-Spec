"""Validation helpers for user-facing scientific warnings."""

from __future__ import annotations

import numpy as np


def saturation_warning(intensity: np.ndarray, top_fraction: float = 0.01) -> str | None:
    """Detect flat-topped high intensity values that may indicate detector saturation."""

    y = np.asarray(intensity, dtype=float)
    if len(y) < 10:
        return None
    ymax = np.max(y)
    if ymax <= 0:
        return None
    near_top = np.mean(y > ymax * (1.0 - top_fraction))
    if near_top > 0.04:
        return "Saturation suspected from flat-topped high-intensity region"
    return None

