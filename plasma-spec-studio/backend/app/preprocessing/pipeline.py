"""Apply serialized preprocessing operations."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.core.fitting_utils import crop_window
from app.core.spectrum import Spectrum
from app.preprocessing.baseline import (
    baseline_als_corrected,
    manual_anchor_baseline,
    polynomial_baseline,
)
from app.preprocessing.calibration import apply_wavelength_calibration_pairs, apply_wavelength_shift
from app.preprocessing.normalization import normalize
from app.preprocessing.smoothing import moving_average, savitzky_golay
from app.preprocessing.spike_removal import remove_spikes


def apply_preprocessing_operations(
    spectrum: Spectrum,
    operations: list[dict[str, Any]],
    background: Spectrum | None = None,
) -> Spectrum:
    """Apply a list of preprocessing operations to a spectrum."""

    current = spectrum
    for operation in operations:
        name = operation.get("operation") or operation.get("name")
        params = operation.get("params") or {}
        wave = current.wavelength_nm
        signal = current.intensity

        if name == "crop":
            out_wave, out_signal = crop_window(wave, signal, params["window_nm"])
        elif name == "background_subtract":
            if background is None:
                raise ValueError("background_subtract requires a background spectrum")
            interpolated = np.interp(wave, background.wavelength_nm, background.intensity)
            out_wave, out_signal = wave, signal - interpolated
        elif name == "baseline_polynomial":
            out_signal, _ = polynomial_baseline(wave, signal, order=params.get("order", 2))
            out_wave = wave
        elif name == "baseline_als":
            lam = params.get("lambda", params.get("lam", 100_000.0))
            out_signal, _ = baseline_als_corrected(
                signal, lam=lam, p=params.get("p", 0.01), n_iter=params.get("n_iter", 10)
            )
            out_wave = wave
        elif name == "baseline_manual":
            out_signal, _ = manual_anchor_baseline(wave, signal, params["anchors"])
            out_wave = wave
        elif name == "normalize":
            out_signal = normalize(wave, signal, method=params.get("method", "max"), window_nm=params.get("window_nm"))
            out_wave = wave
        elif name == "smooth_savgol":
            out_signal = savitzky_golay(
                signal,
                window_points=params.get("window_points", 9),
                polyorder=params.get("polyorder", 2),
            )
            out_wave = wave
        elif name == "smooth_moving_average":
            out_signal = moving_average(signal, window_points=params.get("window_points", 5))
            out_wave = wave
        elif name == "remove_spikes":
            out_signal, _ = remove_spikes(
                signal,
                window_points=params.get("window_points", 5),
                threshold_sigma=params.get("threshold_sigma", 6.0),
            )
            out_wave = wave
        elif name == "wavelength_shift":
            out_wave = apply_wavelength_shift(wave, params.get("shift_nm", 0.0))
            out_signal = signal
        elif name == "wavelength_calibration":
            out_wave = apply_wavelength_calibration_pairs(
                wave,
                pairs=params.get("pairs", []),
                order=params.get("order", 1),
            )
            out_signal = signal
        else:
            raise ValueError(f"unsupported preprocessing operation: {name}")

        current = current.with_data(out_wave, out_signal, name, params)
    return current
