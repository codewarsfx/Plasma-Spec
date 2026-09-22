"""Shared fitting metrics and quality checks."""

from __future__ import annotations

from typing import Any

import numpy as np


def crop_window(
    wavelength_nm: np.ndarray, intensity: np.ndarray, window_nm: tuple[float, float] | list[float]
) -> tuple[np.ndarray, np.ndarray]:
    """Crop wavelength/intensity arrays to an inclusive wavelength window."""

    lo, hi = float(window_nm[0]), float(window_nm[1])
    if lo >= hi:
        raise ValueError("window min must be smaller than window max")
    wave = np.asarray(wavelength_nm, dtype=float)
    signal = np.asarray(intensity, dtype=float)
    mask = (wave >= lo) & (wave <= hi)
    if mask.sum() < 3:
        raise ValueError("selected wavelength window contains too few points")
    return wave[mask], signal[mask]


def fit_metrics(y: np.ndarray, y_fit: np.ndarray) -> dict[str, float]:
    """Calculate common residual metrics for fit quality reporting."""

    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)
    residual = y - y_fit
    rmse = float(np.sqrt(np.mean(residual**2)))
    dynamic_range = float(np.max(y) - np.min(y))
    normalized_rmse = rmse / dynamic_range if dynamic_range > 0 else float("inf")
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    max_residual = float(np.max(np.abs(residual)))
    snr = estimate_snr(y)
    return {
        "rmse": rmse,
        "normalized_rmse": float(normalized_rmse),
        "r2": float(r2),
        "snr": float(snr),
        "max_residual": max_residual,
    }


def estimate_snr(y: np.ndarray) -> float:
    """Estimate local SNR from signal range and edge noise."""

    y = np.asarray(y, dtype=float)
    if len(y) < 8:
        noise = np.std(y - np.mean(y))
    else:
        edge_count = max(3, len(y) // 10)
        edges = np.concatenate([y[:edge_count], y[-edge_count:]])
        noise = np.std(edges - np.median(edges))
    signal = np.max(y) - np.median(y)
    if noise <= 0:
        return float("inf")
    return float(signal / noise)


def classify_fit_quality(metrics: dict[str, float], warnings: list[str]) -> str:
    """Classify fit quality into good/warning/bad."""

    if metrics.get("snr", 0.0) < 3 or metrics.get("normalized_rmse", 1.0) > 0.35:
        return "bad"
    if warnings or metrics.get("snr", 0.0) < 8 or metrics.get("normalized_rmse", 1.0) > 0.12:
        return "warning"
    return "good"


def boundary_warnings(
    params: dict[str, float], bounds: dict[str, tuple[float, float]], relative_tol: float = 0.02
) -> list[str]:
    """Return warnings when fitted parameters are close to configured bounds."""

    warnings: list[str] = []
    for name, value in params.items():
        if name not in bounds:
            continue
        lo, hi = bounds[name]
        span = hi - lo
        if span <= 0:
            continue
        if abs(value - lo) / span < relative_tol or abs(hi - value) / span < relative_tol:
            warnings.append(f"Fit parameter hit boundary or is very close to boundary: {name}")
    return warnings


def serializable_array_pair(wavelength_nm: np.ndarray, values: np.ndarray) -> list[dict[str, float]]:
    """Return a compact list of wavelength/value mappings for API responses."""

    return [
        {"wavelength_nm": float(w), "value": float(v)}
        for w, v in zip(np.asarray(wavelength_nm), np.asarray(values), strict=True)
    ]


def flatten_result_for_csv(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten common nested result fields into one CSV-friendly row."""

    row: dict[str, Any] = {
        "spectrum_id": result.get("spectrum_id"),
        "filename": result.get("filename"),
        "diagnostic": result.get("diagnostic"),
        "fit_quality": result.get("fit_quality"),
        "warnings": "; ".join(result.get("warnings") or []),
    }
    for key, value in (result.get("parameters") or {}).items():
        row[key] = value
    for key, value in (result.get("metrics") or {}).items():
        row[key] = value
    metadata = result.get("metadata") or {}
    for key, value in metadata.items():
        row[f"metadata_{key}"] = value
    if result.get("error"):
        row["error"] = result["error"]
    return row

