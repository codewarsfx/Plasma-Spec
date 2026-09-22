"""Atomic line identification against the bundled NIST-derived catalog."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import find_peaks

from app.core.fitting_utils import crop_window
from app.core.spectrum import Spectrum
from app.databases.atomic import store as atomic_store


def identify_lines(
    spectrum: Spectrum,
    window_nm: tuple[float, float] | list[float] | None = None,
    threshold_rel: float = 0.1,
    tolerance_nm: float = 0.25,
    species: list[str] | None = None,
) -> dict[str, Any]:
    """Detect local maxima and return possible line assignments.

    Assignments are deliberately labeled as possible matches because OES line
    identification depends on resolution, chemistry, calibration, and blends.
    """

    if window_nm is None:
        x = spectrum.wavelength_nm
        y = spectrum.intensity
    else:
        x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    y = np.asarray(y, dtype=float)
    if len(y) < 3:
        raise ValueError("line identification requires at least three points")
    prominence = max(float(np.ptp(y)) * threshold_rel, 1e-12)
    peak_indices, properties = find_peaks(y, prominence=prominence)

    detected: list[dict[str, Any]] = []
    for peak_idx, prominence_value in zip(
        peak_indices, properties.get("prominences", []), strict=False
    ):
        wavelength = float(x[peak_idx])
        matches = atomic_store.search_lines(
            species=species,
            near_nm=wavelength,
            tolerance_nm=tolerance_nm,
            max_results=20,
        )
        for match in matches:
            match["delta_nm"] = float(
                abs(float(match["wavelength_air_nm"]) - wavelength)
            )
        matches.sort(key=lambda item: item["delta_nm"])
        detected.append(
            {
                "detected_wavelength_nm": wavelength,
                "intensity": float(y[peak_idx]),
                "prominence": float(prominence_value),
                "possible_assignments": matches,
            }
        )

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "diagnostic": "line_identification",
        "window_nm": list(window_nm) if window_nm else None,
        "threshold_rel": threshold_rel,
        "tolerance_nm": tolerance_nm,
        "detected_peaks": detected,
        "warnings": [
            "Assignments are possible matches, not final species identifications. "
            "Resolution, calibration, and blends affect correctness."
        ],
    }

