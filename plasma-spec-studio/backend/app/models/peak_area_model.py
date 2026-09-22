"""Peak intensity and area tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.core.constants import DIAGNOSTIC_WINDOWS_NM
from app.core.fitting_utils import crop_window, estimate_snr, serializable_array_pair
from app.core.spectrum import Spectrum


DEFAULT_PEAK_WINDOWS = {
    "OH band": DIAGNOSTIC_WINDOWS_NM["OH(A-X)"],
    "N2 337 nm": DIAGNOSTIC_WINDOWS_NM["N2(C-B) 337"],
    "N2+ 391 nm": DIAGNOSTIC_WINDOWS_NM["N2+ first negative"],
    "Hbeta": DIAGNOSTIC_WINDOWS_NM["Hbeta"],
    "Halpha": DIAGNOSTIC_WINDOWS_NM["Halpha"],
    "O 777 nm": DIAGNOSTIC_WINDOWS_NM["O 777"],
    "O 844 nm": DIAGNOSTIC_WINDOWS_NM["O 844"],
}


def analyze_peak_window(
    spectrum: Spectrum,
    window_nm: tuple[float, float] | list[float],
    name: str = "custom_peak",
) -> dict[str, Any]:
    """Calculate max intensity, integrated area, baseline-subtracted area, and SNR."""

    x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    baseline = _local_linear_baseline(x, y)
    corrected = y - baseline
    max_idx = int(np.argmax(y))
    corrected_max_idx = int(np.argmax(corrected))
    result = {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": "peak_area",
        "peak_name": name,
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "parameters": {
            "max_intensity": float(np.max(y)),
            "max_wavelength_nm": float(x[max_idx]),
            "integrated_area": float(np.trapezoid(y, x)),
            "baseline_subtracted_area": float(np.trapezoid(corrected, x)),
            "baseline_subtracted_peak_height": float(corrected[corrected_max_idx]),
            "baseline_subtracted_peak_wavelength_nm": float(x[corrected_max_idx]),
            "snr": float(estimate_snr(corrected)),
        },
        "metrics": {"snr": float(estimate_snr(corrected))},
        "fit_quality": "good" if estimate_snr(corrected) >= 5 else "warning",
        "warnings": [] if estimate_snr(corrected) >= 5 else ["Weak signal or low SNR"],
        "preprocessing_history": spectrum.preprocessing_history,
        "measured_curve": serializable_array_pair(x, y),
        "baseline_curve": serializable_array_pair(x, baseline),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


def intensity_ratio(
    spectrum: Spectrum,
    numerator_window_nm: tuple[float, float] | list[float],
    denominator_window_nm: tuple[float, float] | list[float],
) -> dict[str, float | None]:
    """Calculate a baseline-subtracted area ratio between two windows."""

    numerator = analyze_peak_window(spectrum, numerator_window_nm, "numerator")
    denominator = analyze_peak_window(spectrum, denominator_window_nm, "denominator")
    num_area = numerator["parameters"]["baseline_subtracted_area"]
    den_area = denominator["parameters"]["baseline_subtracted_area"]
    return {
        "numerator_area": num_area,
        "denominator_area": den_area,
        "ratio": None if den_area == 0 else num_area / den_area,
    }


def _local_linear_baseline(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    edge_count = max(2, len(x) // 10)
    left = float(np.median(y[:edge_count]))
    right = float(np.median(y[-edge_count:]))
    return np.interp(x, [x[0], x[-1]], [left, right])
