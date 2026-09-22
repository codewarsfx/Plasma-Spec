"""Atomic forward spectrum model using the local NIST catalog.

This is a relative, optically thin LTE-style model for OES work:

    I_ul ∝ species_scale * g_u * A_ul * exp(-c2 E_u / T_exc) / lambda

The result is not absolute radiance. It is intended for fitting excitation
temperature, instrumental width, wavelength shift, baseline, and relative
species scales against measured spectra when the assumptions are acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.optimize import least_squares, lsq_linear

from app.core.fitting_utils import (
    boundary_warnings,
    classify_fit_quality,
    crop_window,
    fit_metrics,
    serializable_array_pair,
)
from app.core.line_shapes import (
    gaussian,
    gamma_from_lorentzian_fwhm,
    sigma_from_gaussian_fwhm,
    voigt,
)
from app.core.spectrum import Spectrum
from app.databases.atomic import store as atomic_store
from app.models.boltzmann import SECOND_RADIATION_CONSTANT_CM_K


InstrumentProfile = Literal["gaussian", "voigt"]
BaselineOrder = Literal[0, 1]


@dataclass(frozen=True)
class AtomicModelSet:
    """Prepared atomic transitions and accounting for a selected model."""

    lines: pd.DataFrame
    available_count: int
    physics_ready_count: int
    used_count: int
    excluded_missing_physics: int
    truncated: bool


def fit_atomic_forward_model(
    spectrum: Spectrum,
    *,
    species: list[str],
    window_nm: tuple[float, float] | list[float],
    initial_temperature_K: float = 9000.0,
    temperature_bounds_K: tuple[float, float] | list[float] = (1000.0, 30_000.0),
    fit_temperature: bool = True,
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_fwhm_nm: float = 0.15,
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.02, 2.0),
    fit_instrument_fwhm: bool = True,
    instrument_lorentz_fwhm_nm: float = 0.0,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.0, 2.0),
    fit_instrument_lorentz: bool = False,
    wavelength_shift_nm: float = 0.0,
    wavelength_shift_bounds_nm: tuple[float, float] | list[float] = (-1.0, 1.0),
    fit_wavelength_shift: bool = True,
    species_weights: dict[str, float] | None = None,
    fit_species_scales: bool = True,
    baseline_order: BaselineOrder = 1,
    max_lines: int = 3000,
    top_contributions: int = 40,
) -> dict[str, Any]:
    """Fit a relative atomic emission model against a measured spectrum."""

    _validate_profile(instrument_profile, instrument_lorentz_fwhm_nm)
    species = _normalise_species(species)
    if not species:
        raise ValueError("at least one atomic species is required")
    if baseline_order not in (0, 1):
        raise ValueError("baseline_order must be 0 or 1")

    x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    line_set = prepare_atomic_model_lines(
        species=species,
        window_nm=window_nm,
        temperature_K=initial_temperature_K,
        max_lines=max_lines,
        margin_nm=_line_margin_nm(
            instrument_fwhm_nm=instrument_fwhm_nm,
            instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
            shift_bounds_nm=wavelength_shift_bounds_nm,
        ),
    )
    if line_set.lines.empty:
        raise ValueError(
            "no physics-ready NIST lines found in this window; refresh NIST coverage "
            "or choose species with A_ki, E_k, and g_k values"
        )

    fixed_weights = _normalise_weights(species, species_weights)
    nonlinear_spec = _build_nonlinear_spec(
        initial_temperature_K=initial_temperature_K,
        temperature_bounds_K=temperature_bounds_K,
        fit_temperature=fit_temperature,
        instrument_fwhm_nm=instrument_fwhm_nm,
        instrument_fwhm_bounds_nm=instrument_fwhm_bounds_nm,
        fit_instrument_fwhm=fit_instrument_fwhm,
        instrument_profile=instrument_profile,
        instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        instrument_lorentz_fwhm_bounds_nm=instrument_lorentz_fwhm_bounds_nm,
        fit_instrument_lorentz=fit_instrument_lorentz,
        wavelength_shift_nm=wavelength_shift_nm,
        wavelength_shift_bounds_nm=wavelength_shift_bounds_nm,
        fit_wavelength_shift=fit_wavelength_shift,
    )
    fixed_params = {
        "temperature_K": float(initial_temperature_K),
        "instrument_fwhm_nm": float(instrument_fwhm_nm),
        "instrument_lorentz_fwhm_nm": float(instrument_lorentz_fwhm_nm),
        "wavelength_shift_nm": float(wavelength_shift_nm),
    }
    best_linear: dict[str, Any] | None = None

    def solve_linear(params: dict[str, float]) -> dict[str, Any]:
        merged = {**fixed_params, **params}
        templates = atomic_species_templates(
            x,
            line_set.lines,
            species=species,
            temperature_K=merged["temperature_K"],
            instrument_profile=instrument_profile,
            instrument_fwhm_nm=merged["instrument_fwhm_nm"],
            instrument_lorentz_fwhm_nm=merged["instrument_lorentz_fwhm_nm"],
            wavelength_shift_nm=merged["wavelength_shift_nm"],
        )
        return _solve_linear_components(
            x=x,
            y=y,
            templates=templates,
            species=species,
            fixed_weights=fixed_weights,
            fit_species_scales=fit_species_scales,
            baseline_order=baseline_order,
        )

    def residual_fn(vector: np.ndarray) -> np.ndarray:
        nonlocal best_linear
        params = _unpack(vector, nonlinear_spec)
        solved = solve_linear(params)
        if best_linear is None or solved["cost"] < best_linear["cost"]:
            best_linear = solved
        return solved["residual"]

    if nonlinear_spec:
        p0 = np.array([entry["initial"] for entry in nonlinear_spec], dtype=float)
        lo = np.array([entry["lower"] for entry in nonlinear_spec], dtype=float)
        hi = np.array([entry["upper"] for entry in nonlinear_spec], dtype=float)
        fit = least_squares(
            residual_fn,
            p0,
            bounds=(lo, hi),
            max_nfev=100,
            xtol=1e-5,
            ftol=1e-5,
        )
        nonlinear_params = _unpack(fit.x, nonlinear_spec)
        final = solve_linear(nonlinear_params)
        solver = {
            "outer_status": int(fit.status),
            "outer_cost": float(fit.cost),
            "outer_nfev": int(fit.nfev),
            "linear_cost": float(final["cost"]),
        }
        parameter_stderr = _stderr_from_jacobian(fit, nonlinear_spec)
    else:
        nonlinear_params = {}
        final = solve_linear({})
        solver = {
            "outer_status": 0,
            "outer_cost": float(final["cost"]),
            "outer_nfev": 0,
            "linear_cost": float(final["cost"]),
        }
        parameter_stderr = {}

    params = {**fixed_params, **nonlinear_params}
    y_fit = final["y_fit"]
    metrics = fit_metrics(y, y_fit)
    result_parameters = {
        "temperature_K": float(params["temperature_K"]),
        "instrument_fwhm_nm": float(params["instrument_fwhm_nm"]),
        "instrument_lorentz_fwhm_nm": (
            float(params["instrument_lorentz_fwhm_nm"])
            if instrument_profile == "voigt"
            else None
        ),
        "wavelength_shift_nm": float(params["wavelength_shift_nm"]),
        "baseline_0": float(final["baseline_0"]),
        "baseline_1": float(final["baseline_1"]),
        "species_scales": final["species_scales"],
        "fit_species_scales": bool(fit_species_scales),
        "baseline_order": int(baseline_order),
        "line_count_available": int(line_set.available_count),
        "line_count_physics_ready": int(line_set.physics_ready_count),
        "line_count_used": int(line_set.used_count),
        "excluded_missing_physics": int(line_set.excluded_missing_physics),
        "max_lines": int(max_lines),
    }

    bounds_for_warnings = {
        entry["name"]: (float(entry["lower"]), float(entry["upper"]))
        for entry in nonlinear_spec
    }
    warnings = boundary_warnings(
        {
            "temperature_K": result_parameters["temperature_K"],
            "instrument_fwhm_nm": result_parameters["instrument_fwhm_nm"],
            "instrument_lorentz_fwhm_nm": result_parameters["instrument_lorentz_fwhm_nm"] or 0.0,
            "wavelength_shift_nm": result_parameters["wavelength_shift_nm"],
        },
        bounds_for_warnings,
    )
    warnings.extend(_model_warnings(line_set, final["species_scales"], metrics))

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": "atomic_forward_model",
        "model": "optically_thin_lte_atomic",
        "species": ", ".join(species),
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "database_kind": "nist_catalog",
        "database_source": "atomic catalog (bundled + nist_live + user overrides)",
        "transition_count": int(line_set.used_count),
        "instrument_profile": instrument_profile,
        "parameters": result_parameters,
        "parameter_stderr": parameter_stderr,
        "metrics": metrics,
        "fit_quality": classify_fit_quality(metrics, warnings),
        "warnings": warnings,
        "analysis_notes": [
            "Relative optically thin LTE upper-state model; not absolute radiance.",
            "Species scales absorb partition functions, collection efficiency, path length, and calibration.",
            "Self-absorption, radiation transport, quenching, and non-Boltzmann kinetics are not included.",
        ],
        "line_contributions": line_contribution_rows(
            line_set.lines,
            species_scales=final["species_scales"],
            temperature_K=float(params["temperature_K"]),
            top_n=top_contributions,
        ),
        "solver": {
            **solver,
            "fit_temperature": bool(fit_temperature),
            "fit_wavelength_shift": bool(fit_wavelength_shift),
            "fit_instrument_fwhm": bool(fit_instrument_fwhm),
            "fit_instrument_lorentz": bool(fit_instrument_lorentz),
        },
        "preprocessing_history": spectrum.preprocessing_history,
        "fit_curve": serializable_array_pair(x, y_fit),
        "measured_curve": serializable_array_pair(x, y),
        "residual_curve": serializable_array_pair(x, y - y_fit),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def simulate_atomic_spectrum(
    *,
    species: list[str],
    window_nm: tuple[float, float] | list[float],
    temperature_K: float = 9000.0,
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_fwhm_nm: float = 0.15,
    instrument_lorentz_fwhm_nm: float = 0.0,
    wavelength_shift_nm: float = 0.0,
    species_weights: dict[str, float] | None = None,
    grid_step_nm: float = 0.02,
    max_lines: int = 3000,
    top_contributions: int = 40,
) -> dict[str, Any]:
    """Generate a standalone relative synthetic atomic spectrum."""

    _validate_profile(instrument_profile, instrument_lorentz_fwhm_nm)
    species = _normalise_species(species)
    if not species:
        raise ValueError("at least one atomic species is required")
    if grid_step_nm <= 0:
        raise ValueError("grid_step_nm must be positive")
    lo, hi = float(window_nm[0]), float(window_nm[1])
    if lo >= hi:
        raise ValueError("window_nm must be ordered low < high")
    n_points = int(np.floor((hi - lo) / float(grid_step_nm))) + 1
    if n_points < 3 or n_points > 100_000:
        raise ValueError("grid would contain too few or too many points")
    x = np.linspace(lo, hi, n_points)
    line_set = prepare_atomic_model_lines(
        species=species,
        window_nm=window_nm,
        temperature_K=temperature_K,
        max_lines=max_lines,
        margin_nm=_line_margin_nm(
            instrument_fwhm_nm=instrument_fwhm_nm,
            instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
            shift_bounds_nm=(wavelength_shift_nm, wavelength_shift_nm),
        ),
    )
    if line_set.lines.empty:
        raise ValueError("no physics-ready NIST lines found in this window")

    templates = atomic_species_templates(
        x,
        line_set.lines,
        species=species,
        temperature_K=temperature_K,
        instrument_profile=instrument_profile,
        instrument_fwhm_nm=instrument_fwhm_nm,
        instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        wavelength_shift_nm=wavelength_shift_nm,
    )
    weights = _normalise_weights(species, species_weights)
    y = np.zeros_like(x)
    for item in species:
        y += weights[item] * templates.get(item, np.zeros_like(x))
    max_y = float(np.max(y)) if len(y) else 0.0
    if max_y > 0:
        y = y / max_y

    return {
        "diagnostic": "atomic_forward_simulation",
        "model": "optically_thin_lte_atomic",
        "species": ", ".join(species),
        "window_nm": [lo, hi],
        "database_kind": "nist_catalog",
        "database_source": "atomic catalog (bundled + nist_live + user overrides)",
        "transition_count": int(line_set.used_count),
        "instrument_profile": instrument_profile,
        "parameters": {
            "temperature_K": float(temperature_K),
            "instrument_fwhm_nm": float(instrument_fwhm_nm),
            "instrument_lorentz_fwhm_nm": (
                float(instrument_lorentz_fwhm_nm) if instrument_profile == "voigt" else None
            ),
            "wavelength_shift_nm": float(wavelength_shift_nm),
            "species_scales": weights,
            "line_count_available": int(line_set.available_count),
            "line_count_physics_ready": int(line_set.physics_ready_count),
            "line_count_used": int(line_set.used_count),
            "excluded_missing_physics": int(line_set.excluded_missing_physics),
            "max_lines": int(max_lines),
        },
        "metrics": {"max_intensity": float(np.max(y)), "integrated_intensity": float(np.trapezoid(y, x))},
        "fit_quality": "good",
        "warnings": _model_warnings(line_set, weights, {}),
        "analysis_notes": [
            "Relative optically thin LTE upper-state model; not absolute radiance.",
            "Species scales absorb partition functions, collection efficiency, path length, and calibration.",
            "Self-absorption, radiation transport, quenching, and non-Boltzmann kinetics are not included.",
        ],
        "line_contributions": line_contribution_rows(
            line_set.lines,
            species_scales=weights,
            temperature_K=float(temperature_K),
            top_n=top_contributions,
        ),
        "fit_curve": serializable_array_pair(x, y),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def prepare_atomic_model_lines(
    *,
    species: list[str],
    window_nm: tuple[float, float] | list[float],
    temperature_K: float,
    max_lines: int,
    margin_nm: float,
) -> AtomicModelSet:
    """Load, filter, and rank physics-ready atomic lines for the forward model."""

    if max_lines < 1:
        raise ValueError("max_lines must be positive")
    frame = atomic_store.load_catalog().copy()
    species_set = {item.lower() for item in species}
    lo = float(window_nm[0]) - float(margin_nm)
    hi = float(window_nm[1]) + float(margin_nm)
    frame = frame[
        frame["species"].astype(str).str.lower().isin(species_set)
        & (frame["wavelength_air_nm"] >= lo)
        & (frame["wavelength_air_nm"] <= hi)
    ].copy()
    available_count = int(len(frame))
    if frame.empty:
        return AtomicModelSet(frame, 0, 0, 0, 0, False)

    frame = _prefer_live_or_user_rows(frame)
    for column in ("wavelength_air_nm", "A_ki_s_1", "E_k_cm1", "g_k"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    ready = (
        frame["wavelength_air_nm"].notna()
        & frame["A_ki_s_1"].notna()
        & frame["E_k_cm1"].notna()
        & frame["g_k"].notna()
        & (frame["A_ki_s_1"] > 0)
        & (frame["g_k"] > 0)
        & (frame["E_k_cm1"] >= 0)
    )
    physics_ready = frame.loc[ready].copy()
    physics_ready_count = int(len(physics_ready))
    if physics_ready.empty:
        return AtomicModelSet(
            physics_ready,
            available_count,
            0,
            0,
            available_count,
            False,
        )

    physics_ready["_rank_strength"] = _line_strength_factor(physics_ready, temperature_K)
    physics_ready = physics_ready.sort_values("_rank_strength", ascending=False)
    truncated = len(physics_ready) > max_lines
    if truncated:
        physics_ready = physics_ready.head(max_lines).copy()
    physics_ready = physics_ready.drop(columns=["_rank_strength"], errors="ignore")
    return AtomicModelSet(
        lines=physics_ready.reset_index(drop=True),
        available_count=available_count,
        physics_ready_count=physics_ready_count,
        used_count=int(len(physics_ready)),
        excluded_missing_physics=available_count - physics_ready_count,
        truncated=truncated,
    )


def atomic_species_templates(
    x_nm: np.ndarray,
    lines: pd.DataFrame,
    *,
    species: list[str],
    temperature_K: float,
    instrument_profile: InstrumentProfile,
    instrument_fwhm_nm: float,
    instrument_lorentz_fwhm_nm: float,
    wavelength_shift_nm: float,
) -> dict[str, np.ndarray]:
    """Return one normalized synthetic template per species."""

    x = np.asarray(x_nm, dtype=float)
    templates = {item: np.zeros_like(x) for item in species}
    sigma = sigma_from_gaussian_fwhm(instrument_fwhm_nm)
    gamma = gamma_from_lorentzian_fwhm(max(float(instrument_lorentz_fwhm_nm), 1e-12))
    strengths = _line_strength_factor(lines, temperature_K).to_numpy(dtype=float)
    for (_, row), strength in zip(lines.iterrows(), strengths, strict=True):
        item = str(row["species"]).strip()
        if item not in templates or not np.isfinite(strength) or strength <= 0:
            continue
        center = float(row["wavelength_air_nm"]) + float(wavelength_shift_nm)
        if instrument_profile == "gaussian":
            profile = gaussian(x, center, sigma)
        else:
            profile = voigt(x, center, sigma, gamma)
        templates[item] += strength * profile
    for item, values in list(templates.items()):
        max_value = float(np.max(values)) if len(values) else 0.0
        if max_value > 0:
            templates[item] = values / max_value
    return templates


def line_contribution_rows(
    lines: pd.DataFrame,
    *,
    species_scales: dict[str, float],
    temperature_K: float,
    top_n: int,
) -> list[dict[str, Any]]:
    """Return the strongest modeled lines with provenance and relative strength."""

    if lines.empty or top_n <= 0:
        return []
    frame = lines.copy()
    frame["_raw_strength"] = _line_strength_factor(frame, temperature_K)
    max_by_species = frame.groupby("species")["_raw_strength"].transform("max").replace(0.0, np.nan)
    frame["_relative_strength"] = (frame["_raw_strength"] / max_by_species).fillna(0.0)
    frame["_relative_strength"] *= frame["species"].astype(str).map(species_scales).fillna(0.0)
    max_strength = float(frame["_relative_strength"].max())
    if max_strength > 0:
        frame["_relative_strength"] = frame["_relative_strength"] / max_strength
    frame = frame.sort_values("_relative_strength", ascending=False).head(int(top_n))
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "species": str(row.get("species", "")),
                "wavelength_air_nm": float(row["wavelength_air_nm"]),
                "relative_strength": float(row["_relative_strength"]),
                "A_ki_s_1": _optional_float(row.get("A_ki_s_1")),
                "E_k_cm1": _optional_float(row.get("E_k_cm1")),
                "g_k": _optional_float(row.get("g_k")),
                "transition": _optional_str(row.get("transition")),
                "source_tag": _optional_str(row.get("source_tag")),
                "line_ref": _optional_str(row.get("line_ref")),
            }
        )
    return rows


def _solve_linear_components(
    *,
    x: np.ndarray,
    y: np.ndarray,
    templates: dict[str, np.ndarray],
    species: list[str],
    fixed_weights: dict[str, float],
    fit_species_scales: bool,
    baseline_order: BaselineOrder,
) -> dict[str, Any]:
    x_centered = x - float(np.mean(x))
    if fit_species_scales:
        template_columns = [templates[item] for item in species]
        design_columns = [*template_columns, np.ones_like(x)]
        lower = [0.0] * len(species) + [-np.inf]
        upper = [np.inf] * (len(species) + 1)
        if baseline_order == 1:
            design_columns.append(x_centered)
            lower.append(-np.inf)
            upper.append(np.inf)
        design = np.column_stack(design_columns)
        fit = lsq_linear(
            design,
            y,
            bounds=(np.array(lower), np.array(upper)),
            max_iter=200,
            lsmr_tol="auto",
        )
        coeffs = fit.x
        species_scales = {
            item: float(coeffs[index])
            for index, item in enumerate(species)
        }
        baseline_0 = float(coeffs[len(species)])
        baseline_1 = float(coeffs[len(species) + 1]) if baseline_order == 1 else 0.0
        y_fit = design @ coeffs
    else:
        template = np.zeros_like(x)
        for item in species:
            template += fixed_weights[item] * templates[item]
        design_columns = [template, np.ones_like(x)]
        if baseline_order == 1:
            design_columns.append(x_centered)
        design = np.column_stack(design_columns)
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        species_scale = max(float(coeffs[0]), 0.0)
        species_scales = {
            item: float(species_scale * fixed_weights[item])
            for item in species
        }
        baseline_0 = float(coeffs[1])
        baseline_1 = float(coeffs[2]) if baseline_order == 1 else 0.0
        y_fit = design @ coeffs
    return {
        "species_scales": species_scales,
        "baseline_0": baseline_0,
        "baseline_1": baseline_1,
        "y_fit": y_fit,
        "residual": y_fit - y,
        "cost": float(0.5 * np.sum((y_fit - y) ** 2)),
    }


def _build_nonlinear_spec(
    *,
    initial_temperature_K: float,
    temperature_bounds_K: tuple[float, float] | list[float],
    fit_temperature: bool,
    instrument_fwhm_nm: float,
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float],
    fit_instrument_fwhm: bool,
    instrument_profile: InstrumentProfile,
    instrument_lorentz_fwhm_nm: float,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float],
    fit_instrument_lorentz: bool,
    wavelength_shift_nm: float,
    wavelength_shift_bounds_nm: tuple[float, float] | list[float],
    fit_wavelength_shift: bool,
) -> list[dict[str, float]]:
    entries: list[dict[str, float]] = []
    if fit_temperature:
        entries.append(
            _entry("temperature_K", initial_temperature_K, temperature_bounds_K)
        )
    if fit_instrument_fwhm:
        entries.append(
            _entry("instrument_fwhm_nm", instrument_fwhm_nm, instrument_fwhm_bounds_nm)
        )
    if instrument_profile == "voigt" and fit_instrument_lorentz:
        entries.append(
            _entry(
                "instrument_lorentz_fwhm_nm",
                instrument_lorentz_fwhm_nm,
                instrument_lorentz_fwhm_bounds_nm,
            )
        )
    if fit_wavelength_shift:
        entries.append(
            _entry("wavelength_shift_nm", wavelength_shift_nm, wavelength_shift_bounds_nm)
        )
    return entries


def _entry(name: str, initial: float, bounds: tuple[float, float] | list[float]) -> dict[str, float]:
    lo, hi = float(bounds[0]), float(bounds[1])
    if lo >= hi:
        raise ValueError(f"{name} bounds must be ordered low < high")
    return {
        "name": name,
        "initial": float(np.clip(float(initial), lo, hi)),
        "lower": lo,
        "upper": hi,
    }


def _unpack(vector: np.ndarray, spec: list[dict[str, float]]) -> dict[str, float]:
    return {
        entry["name"]: float(value)
        for entry, value in zip(spec, vector, strict=True)
    }


def _line_strength_factor(lines: pd.DataFrame, temperature_K: float) -> pd.Series:
    temp = max(float(temperature_K), 1e-9)
    energy = pd.to_numeric(lines["E_k_cm1"], errors="coerce")
    degeneracy = pd.to_numeric(lines["g_k"], errors="coerce")
    aki = pd.to_numeric(lines["A_ki_s_1"], errors="coerce")
    wavelength = pd.to_numeric(lines["wavelength_air_nm"], errors="coerce")
    boltzmann = np.exp(-SECOND_RADIATION_CONSTANT_CM_K * energy / temp)
    strength = degeneracy * aki * boltzmann / wavelength
    return pd.Series(strength, index=lines.index).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _prefer_live_or_user_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Avoid double-counting curated bundle rows when live NIST exists."""

    if "source_tag" not in frame.columns:
        return frame
    pieces = []
    for _, group in frame.groupby("species", sort=False):
        tags = set(group["source_tag"].astype(str))
        if "nist_live" in tags:
            group = group[group["source_tag"].astype(str) != "bundled"]
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True) if pieces else frame


def _normalise_species(species: list[str]) -> list[str]:
    seen = set()
    items: list[str] = []
    for raw in species:
        label = " ".join(str(raw).split())
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        items.append(label)
    return items


def _normalise_weights(species: list[str], weights: dict[str, float] | None) -> dict[str, float]:
    raw = {str(k).strip().lower(): float(v) for k, v in (weights or {}).items()}
    output: dict[str, float] = {}
    for item in species:
        value = raw.get(item.lower(), 1.0)
        output[item] = max(float(value), 0.0)
    if all(value == 0.0 for value in output.values()):
        return {item: 1.0 for item in species}
    return output


def _validate_profile(profile: str, lorentz_fwhm_nm: float) -> None:
    if profile not in ("gaussian", "voigt"):
        raise ValueError("instrument_profile must be 'gaussian' or 'voigt'")
    if profile == "voigt" and lorentz_fwhm_nm < 0:
        raise ValueError("instrument_lorentz_fwhm_nm must be non-negative")


def _line_margin_nm(
    *,
    instrument_fwhm_nm: float,
    instrument_lorentz_fwhm_nm: float,
    shift_bounds_nm: tuple[float, float] | list[float],
) -> float:
    shift_margin = max(abs(float(shift_bounds_nm[0])), abs(float(shift_bounds_nm[1])))
    width_margin = 8.0 * max(float(instrument_fwhm_nm), float(instrument_lorentz_fwhm_nm), 0.01)
    return shift_margin + width_margin


def _model_warnings(
    line_set: AtomicModelSet,
    species_scales: dict[str, float],
    metrics: dict[str, float],
) -> list[str]:
    warnings: list[str] = []
    if line_set.excluded_missing_physics > 0:
        warnings.append(
            f"{line_set.excluded_missing_physics} catalog lines excluded because A_ki, E_k, or g_k was missing."
        )
    if line_set.truncated:
        warnings.append(
            f"Model truncated to the strongest {line_set.used_count} physics-ready lines for runtime."
        )
    inactive = [species for species, scale in species_scales.items() if scale <= 1e-12]
    if inactive and len(inactive) < len(species_scales):
        warnings.append(f"Non-negative species fit drove these species to ~0: {', '.join(inactive)}.")
    if metrics and metrics.get("r2", 1.0) < 0.8:
        warnings.append("Atomic forward model explains less than 80% of variance; assumptions or selected species may be wrong.")
    return warnings


def _stderr_from_jacobian(fit: Any, spec: list[dict[str, float]]) -> dict[str, float | None]:
    names = [entry["name"] for entry in spec]
    if not names:
        return {}
    try:
        jac = np.asarray(fit.jac, dtype=float)
        dof = max(1, jac.shape[0] - jac.shape[1])
        covariance = np.linalg.pinv(jac.T @ jac) * (2.0 * float(fit.cost) / dof)
        stderr = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
        return {
            name: (float(value) if np.isfinite(value) else None)
            for name, value in zip(names, stderr, strict=True)
        }
    except Exception:
        return {name: None for name in names}


def _optional_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return None
    return text or None
