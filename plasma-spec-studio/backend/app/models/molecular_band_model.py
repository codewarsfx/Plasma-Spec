"""Database-driven molecular band fitting.

Uses MassiveOES-style SQLite databases (via ``app.databases.molecular.store``)
when they are available, and falls back to the small bundled demo CSV
transitions for environments where the validated databases are not on disk.
The fit result reports ``database_kind`` so callers can warn users when only
the demo data was used.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.optimize import least_squares, lsq_linear

from app.core.constants import DEMO_DATABASE_WARNING
from app.core.fitting_utils import classify_fit_quality, crop_window, fit_metrics, serializable_array_pair
from app.core.line_shapes import (
    gaussian,
    gaussian_fwhm_from_sigma,
    lorentzian_fwhm_from_gamma,
    sigma_from_gaussian_fwhm,
    voigt,
    voigt_fwhm,
)
from app.core.spectrum import Spectrum
from app.databases.molecular import store as molecular_store
from app.models.boltzmann import (
    SECOND_RADIATION_CONSTANT_CM_K,
    rotational_boltzmann_factor,
)


InstrumentProfile = Literal["gaussian", "voigt"]


MOLECULAR_DB_ROOT = Path(__file__).resolve().parents[1] / "databases" / "molecular"


def fit_oh_ax(
    spectrum: Spectrum,
    window_nm: tuple[float, float] | list[float] = (306.0, 312.0),
    initial_trot_K: float = 1200.0,
    trot_bounds_K: tuple[float, float] | list[float] = (250.0, 6000.0),
    instrument_fwhm_nm: float = 0.12,
    wavelength_shift_nm: float = 0.0,
    database_path: str | Path | None = None,
    database_source: Literal["auto", "sqlite", "demo"] = "auto",
    wavelength_shift_bounds_nm: tuple[float, float] | list[float] = (-2.0, 2.0),
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.01, 2.0),
    fit_tvib: bool = False,
    initial_tvib_K: float | None = None,
    tvib_bounds_K: tuple[float, float] | list[float] = (250.0, 10_000.0),
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_lorentz_fwhm_nm: float = 0.0,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.0, 1.0),
    fit_instrument_lorentz: bool = False,
    multi_restart_trot_K: list[float] | None = None,
) -> dict[str, Any]:
    """Fit OH(A-X) rotational (and optionally vibrational) temperature."""

    transitions, source_label, demo = _resolve_transitions(
        species_id="OH_AX",
        window_nm=window_nm,
        explicit_path=database_path,
        database_source=database_source,
        demo_csv=MOLECULAR_DB_ROOT / "OH_AX" / "demo_transitions.csv",
    )
    return fit_molecular_band(
        spectrum=spectrum,
        species_label="OH(A-X)",
        diagnostic="oh_ax",
        window_nm=window_nm,
        transitions=transitions,
        initial_trot_K=initial_trot_K,
        trot_bounds_K=trot_bounds_K,
        instrument_fwhm_nm=instrument_fwhm_nm,
        wavelength_shift_nm=wavelength_shift_nm,
        demo_database=demo,
        database_source_label=source_label,
        tvib_enabled=False,
        wavelength_shift_bounds_nm=wavelength_shift_bounds_nm,
        instrument_fwhm_bounds_nm=instrument_fwhm_bounds_nm,
        fit_tvib=fit_tvib,
        initial_tvib_K=initial_tvib_K,
        tvib_bounds_K=tvib_bounds_K,
        instrument_profile=instrument_profile,
        instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        instrument_lorentz_fwhm_bounds_nm=instrument_lorentz_fwhm_bounds_nm,
        fit_instrument_lorentz=fit_instrument_lorentz,
        multi_restart_trot_K=multi_restart_trot_K,
    )


def fit_n2_cb(
    spectrum: Spectrum,
    window_nm: tuple[float, float] | list[float] = (334.0, 339.0),
    initial_trot_K: float = 1000.0,
    trot_bounds_K: tuple[float, float] | list[float] = (250.0, 8000.0),
    instrument_fwhm_nm: float = 0.12,
    wavelength_shift_nm: float = 0.0,
    database_path: str | Path | None = None,
    database_source: Literal["auto", "sqlite", "demo"] = "auto",
    wavelength_shift_bounds_nm: tuple[float, float] | list[float] = (-2.0, 2.0),
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.01, 2.0),
    fit_tvib: bool = False,
    initial_tvib_K: float | None = None,
    tvib_bounds_K: tuple[float, float] | list[float] = (250.0, 10_000.0),
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_lorentz_fwhm_nm: float = 0.0,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.0, 1.0),
    fit_instrument_lorentz: bool = False,
    multi_restart_trot_K: list[float] | None = None,
) -> dict[str, Any]:
    """Fit N2(C-B) second-positive rotational (and optionally vibrational) temperature."""

    transitions, source_label, demo = _resolve_transitions(
        species_id="N2_CB",
        window_nm=window_nm,
        explicit_path=database_path,
        database_source=database_source,
        demo_csv=MOLECULAR_DB_ROOT / "N2_CB" / "demo_transitions.csv",
    )
    return fit_molecular_band(
        spectrum=spectrum,
        species_label="N2(C-B)",
        diagnostic="n2_cb",
        window_nm=window_nm,
        transitions=transitions,
        initial_trot_K=initial_trot_K,
        trot_bounds_K=trot_bounds_K,
        instrument_fwhm_nm=instrument_fwhm_nm,
        wavelength_shift_nm=wavelength_shift_nm,
        demo_database=demo,
        database_source_label=source_label,
        tvib_enabled=False,
        wavelength_shift_bounds_nm=wavelength_shift_bounds_nm,
        instrument_fwhm_bounds_nm=instrument_fwhm_bounds_nm,
        fit_tvib=fit_tvib,
        initial_tvib_K=initial_tvib_K,
        tvib_bounds_K=tvib_bounds_K,
        instrument_profile=instrument_profile,
        instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        instrument_lorentz_fwhm_bounds_nm=instrument_lorentz_fwhm_bounds_nm,
        fit_instrument_lorentz=fit_instrument_lorentz,
        multi_restart_trot_K=multi_restart_trot_K,
    )


def fit_molecular_band(
    spectrum: Spectrum,
    species_label: str,
    diagnostic: Literal["oh_ax", "n2_cb"] | str,
    window_nm: tuple[float, float] | list[float],
    transitions: pd.DataFrame,
    initial_trot_K: float,
    trot_bounds_K: tuple[float, float] | list[float],
    instrument_fwhm_nm: float,
    wavelength_shift_nm: float,
    demo_database: bool,
    database_source_label: str = "demo_csv",
    tvib_enabled: bool = False,
    wavelength_shift_bounds_nm: tuple[float, float] | list[float] = (-2.0, 2.0),
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.01, 2.0),
    fit_tvib: bool = False,
    initial_tvib_K: float | None = None,
    tvib_bounds_K: tuple[float, float] | list[float] = (250.0, 10_000.0),
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_lorentz_fwhm_nm: float = 0.0,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.0, 1.0),
    fit_instrument_lorentz: bool = False,
    multi_restart_trot_K: list[float] | None = None,
) -> dict[str, Any]:
    """Fit a database-driven molecular band against ``spectrum``.

    Two-temperature mode (``fit_tvib=True``) adds Tvib as a free parameter;
    this requires the transitions DataFrame to carry separate
    ``e_rot_upper_cm1`` and ``e_vib_upper_cm1`` columns (provided by
    ``databases.molecular.store``).

    Voigt instrument profile (``instrument_profile='voigt'``) adds a
    Lorentzian-width component; set ``fit_instrument_lorentz=True`` to fit it
    too, or fix it to ``instrument_lorentz_fwhm_nm``.

    ``multi_restart_trot_K`` runs the fit from each provided initial Trot and
    returns the best one. This escapes local minima that single-restart fits
    can fall into when bands overlap.
    """

    x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    transitions = transitions[
        (transitions["wavelength_nm"] >= window_nm[0] - 2.0)
        & (transitions["wavelength_nm"] <= window_nm[1] + 2.0)
    ]
    if transitions.empty:
        raise ValueError(f"no transitions available for {species_label} in selected window")

    if fit_tvib and not {"e_rot_upper_cm1", "e_vib_upper_cm1"}.issubset(transitions.columns):
        raise ValueError(
            "fit_tvib=True requires transitions with separate e_rot_upper_cm1 + e_vib_upper_cm1 "
            "columns; the SQLite store provides these, the demo CSV does not."
        )

    spec = _build_param_spec(
        y=y,
        initial_trot_K=initial_trot_K,
        trot_bounds_K=trot_bounds_K,
        fit_tvib=fit_tvib,
        initial_tvib_K=initial_tvib_K,
        tvib_bounds_K=tvib_bounds_K,
        wavelength_shift_nm=wavelength_shift_nm,
        wavelength_shift_bounds_nm=wavelength_shift_bounds_nm,
        instrument_fwhm_nm=instrument_fwhm_nm,
        instrument_fwhm_bounds_nm=instrument_fwhm_bounds_nm,
        instrument_profile=instrument_profile,
        instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        instrument_lorentz_fwhm_bounds_nm=instrument_lorentz_fwhm_bounds_nm,
        fit_instrument_lorentz=fit_instrument_lorentz,
    )
    x0 = float(np.mean(x))

    def synthesize(params: dict[str, float]) -> np.ndarray:
        return molecular_synthetic_spectrum(
            x,
            transitions,
            trot_K=params["trot_K"],
            tvib_K=params.get("tvib_K"),
            instrument_fwhm_nm=params["instrument_fwhm_nm"],
            instrument_profile=instrument_profile,
            instrument_lorentz_fwhm_nm=params.get(
                "instrument_lorentz_fwhm_nm", instrument_lorentz_fwhm_nm
            ),
            wavelength_shift_nm=params["wavelength_shift_nm"],
        )

    def residual_fn(vector: np.ndarray) -> np.ndarray:
        params = _unpack(vector, spec)
        synthetic = synthesize(params)
        baseline = params["baseline_0"] + params["baseline_1"] * (x - x0)
        return baseline + params["scale"] * synthetic - y

    # Multi-restart driver: try each initial Trot and keep the best.
    restart_trots = list(multi_restart_trot_K) if multi_restart_trot_K else [initial_trot_K]
    best: dict[str, Any] | None = None
    restart_log: list[dict[str, Any]] = []
    for restart_trot in restart_trots:
        spec_restart = _override_trot_initial(spec, restart_trot)
        p0 = np.array([entry.initial for entry in spec_restart])
        lo = np.array([entry.lower for entry in spec_restart])
        hi = np.array([entry.upper for entry in spec_restart])
        try:
            fit = least_squares(residual_fn, p0, bounds=(lo, hi), max_nfev=20_000)
        except Exception as exc:  # pragma: no cover - scipy can raise
            restart_log.append({"initial_trot_K": float(restart_trot), "error": str(exc)})
            continue
        cost = float(fit.cost)
        restart_log.append({"initial_trot_K": float(restart_trot), "cost": cost, "status": int(fit.status)})
        if best is None or cost < best["cost"]:
            best = {"cost": cost, "fit": fit, "spec": spec_restart}
    if best is None:
        raise RuntimeError("all molecular fit restarts failed")

    fit = best["fit"]
    spec_final = best["spec"]
    parameters = _unpack(fit.x, spec_final)
    synthetic = synthesize(parameters)
    baseline = parameters["baseline_0"] + parameters["baseline_1"] * (x - x0)
    y_fit = baseline + parameters["scale"] * synthetic
    metrics = fit_metrics(y, y_fit)

    # Parameter uncertainties from the Jacobian covariance.
    parameter_stderr = _parameter_stderr_from_jac(fit, spec_final)

    # Width breakdown for the instrument profile (helps the UI surface this).
    profile_info = _instrument_profile_info(
        instrument_profile, parameters, instrument_lorentz_fwhm_nm
    )

    warnings = molecular_warnings_v2(metrics, parameters, spec_final, demo_database)
    if fit_tvib:
        warnings.append("Two-temperature fit: Trot and Tvib reported separately.")
    else:
        parameters["tvib_K"] = None

    result_parameters: dict[str, Any] = {
        "trot_K": float(parameters["trot_K"]),
        "tvib_K": float(parameters["tvib_K"]) if parameters.get("tvib_K") is not None else None,
        "scale": float(parameters["scale"]),
        "wavelength_shift_nm": float(parameters["wavelength_shift_nm"]),
        "instrument_fwhm_nm": float(parameters["instrument_fwhm_nm"]),
        "instrument_lorentz_fwhm_nm": float(
            parameters.get("instrument_lorentz_fwhm_nm", instrument_lorentz_fwhm_nm)
        ) if instrument_profile == "voigt" else None,
        "baseline_0": float(parameters["baseline_0"]),
        "baseline_1": float(parameters["baseline_1"]),
    }

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": diagnostic,
        "species": species_label,
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "database_kind": "demo" if demo_database else "validated",
        "database_source": database_source_label,
        "transition_count": int(len(transitions)),
        "instrument_profile": instrument_profile,
        "fit_tvib": bool(fit_tvib),
        "parameters": result_parameters,
        "parameter_stderr": parameter_stderr,
        "instrument_widths_nm": profile_info,
        "metrics": metrics,
        "fit_quality": classify_fit_quality(metrics, warnings),
        "warnings": warnings,
        "restart_log": restart_log,
        "n_restarts": len(restart_trots),
        "preprocessing_history": spectrum.preprocessing_history,
        "fit_curve": serializable_array_pair(x, y_fit),
        "measured_curve": serializable_array_pair(x, y),
        "residual_curve": serializable_array_pair(x, y - y_fit),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fit_molecular_state_by_state(
    spectrum: Spectrum,
    species_label: str,
    diagnostic: str,
    window_nm: tuple[float, float] | list[float],
    transitions: pd.DataFrame,
    instrument_fwhm_nm: float,
    wavelength_shift_nm: float,
    demo_database: bool,
    database_source_label: str = "demo_csv",
    *,
    max_states: int = 40,
    min_state_relative_strength: float = 0.0,
    wavelength_shift_bounds_nm: tuple[float, float] | list[float] = (-2.0, 2.0),
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float] = (0.01, 2.0),
    fit_wavelength_shift: bool = True,
    fit_instrument_fwhm: bool = True,
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_lorentz_fwhm_nm: float = 0.0,
) -> dict[str, Any]:
    """Fit independent upper-state populations without assuming Boltzmann form.

    This is the MassiveOES-style "state-by-state" path: each selected upper
    state gets its own non-negative population coefficient. Temperatures are
    not assumed by the forward model; apparent rotational temperatures are
    derived afterward from Boltzmann-plot slopes for each v' manifold.
    """

    if max_states < 1:
        raise ValueError("max_states must be at least 1")
    if not (0.0 <= min_state_relative_strength < 1.0):
        raise ValueError("min_state_relative_strength must be in [0, 1)")
    if instrument_profile not in ("gaussian", "voigt"):
        raise ValueError("instrument_profile must be 'gaussian' or 'voigt'")

    x, y = crop_window(spectrum.wavelength_nm, spectrum.intensity, window_nm)
    transitions = transitions[
        (transitions["wavelength_nm"] >= float(window_nm[0]) - 2.0)
        & (transitions["wavelength_nm"] <= float(window_nm[1]) + 2.0)
    ].copy()
    if transitions.empty:
        raise ValueError(f"no transitions available for {species_label} in selected window")

    transitions = _prepare_state_by_state_transitions(transitions)
    state_rows = _select_state_rows(
        transitions,
        max_states=max_states,
        min_state_relative_strength=min_state_relative_strength,
    )
    if not state_rows:
        raise ValueError("no usable upper states selected for state-by-state fit")

    shift_lo, shift_hi = float(wavelength_shift_bounds_nm[0]), float(wavelength_shift_bounds_nm[1])
    fwhm_lo, fwhm_hi = float(instrument_fwhm_bounds_nm[0]), float(instrument_fwhm_bounds_nm[1])
    if shift_lo >= shift_hi:
        raise ValueError("wavelength_shift_bounds_nm must be ordered low < high")
    if fwhm_lo >= fwhm_hi or fwhm_lo <= 0:
        raise ValueError("instrument_fwhm_bounds_nm must be ordered positive low < high")

    nonlinear_spec: list[_ParamEntry] = []
    if fit_wavelength_shift:
        nonlinear_spec.append(
            _ParamEntry(
                "wavelength_shift_nm",
                float(np.clip(wavelength_shift_nm, shift_lo, shift_hi)),
                shift_lo,
                shift_hi,
            )
        )
    if fit_instrument_fwhm:
        nonlinear_spec.append(
            _ParamEntry(
                "instrument_fwhm_nm",
                float(np.clip(instrument_fwhm_nm, fwhm_lo, fwhm_hi)),
                fwhm_lo,
                fwhm_hi,
            )
        )

    best_linear: dict[str, Any] | None = None

    def solve_for(params: dict[str, float]) -> dict[str, Any]:
        shift = params.get("wavelength_shift_nm", float(wavelength_shift_nm))
        fwhm = params.get("instrument_fwhm_nm", float(instrument_fwhm_nm))
        basis, basis_scales = _state_basis_matrix(
            x,
            transitions,
            state_rows,
            wavelength_shift_nm=shift,
            instrument_fwhm_nm=fwhm,
            instrument_profile=instrument_profile,
            instrument_lorentz_fwhm_nm=instrument_lorentz_fwhm_nm,
        )
        x_centered = x - float(np.mean(x))
        design = np.column_stack([basis, np.ones_like(x), x_centered])
        lower = np.concatenate([np.zeros(len(state_rows)), np.array([-np.inf, -np.inf])])
        upper = np.full(len(state_rows) + 2, np.inf)
        fit = lsq_linear(
            design,
            y,
            bounds=(lower, upper),
            max_iter=250,
            lsmr_tol="auto",
        )
        y_fit = design @ fit.x
        return {
            "fit": fit,
            "basis_scales": basis_scales,
            "coefficients": fit.x[: len(state_rows)],
            "baseline_0": float(fit.x[-2]),
            "baseline_1": float(fit.x[-1]),
            "y_fit": y_fit,
            "residual": y_fit - y,
            "wavelength_shift_nm": float(shift),
            "instrument_fwhm_nm": float(fwhm),
            "cost": float(0.5 * np.sum((y_fit - y) ** 2)),
        }

    def residual_fn(vector: np.ndarray) -> np.ndarray:
        nonlocal best_linear
        params = _unpack(vector, nonlinear_spec)
        solved = solve_for(params)
        if best_linear is None or solved["cost"] < best_linear["cost"]:
            best_linear = solved
        return solved["residual"]

    if nonlinear_spec:
        p0 = np.array([entry.initial for entry in nonlinear_spec])
        lo = np.array([entry.lower for entry in nonlinear_spec])
        hi = np.array([entry.upper for entry in nonlinear_spec])
        nonlinear_fit = least_squares(
            residual_fn,
            p0,
            bounds=(lo, hi),
            max_nfev=80,
            xtol=1e-5,
            ftol=1e-5,
        )
        nonlinear_params = _unpack(nonlinear_fit.x, nonlinear_spec)
        final = solve_for(nonlinear_params)
        nonlinear_status = int(nonlinear_fit.status)
        nonlinear_cost = float(nonlinear_fit.cost)
    else:
        final = solve_for(
            {
                "wavelength_shift_nm": float(wavelength_shift_nm),
                "instrument_fwhm_nm": float(instrument_fwhm_nm),
            }
        )
        nonlinear_status = 0
        nonlinear_cost = final["cost"]

    y_fit = final["y_fit"]
    metrics = fit_metrics(y, y_fit)
    populations = _state_population_rows(state_rows, final["coefficients"], final["basis_scales"])
    boltzmann_by_v = _boltzmann_summaries_by_v(populations)

    parameters: dict[str, Any] = {
        "fit_mode": "state_by_state",
        "state_count": len(populations),
        "max_states": int(max_states),
        "min_state_relative_strength": float(min_state_relative_strength),
        "wavelength_shift_nm": float(final["wavelength_shift_nm"]),
        "instrument_fwhm_nm": float(final["instrument_fwhm_nm"]),
        "instrument_lorentz_fwhm_nm": float(instrument_lorentz_fwhm_nm) if instrument_profile == "voigt" else None,
        "baseline_0": float(final["baseline_0"]),
        "baseline_1": float(final["baseline_1"]),
    }

    warnings = _state_by_state_warnings(
        metrics=metrics,
        parameters=parameters,
        demo_database=demo_database,
        selected_count=len(state_rows),
        available_state_count=int(transitions["_state_key"].nunique()),
        max_states=max_states,
        shift_bounds=(shift_lo, shift_hi),
    )

    return {
        "spectrum_id": spectrum.id,
        "filename": spectrum.filename,
        "metadata": spectrum.metadata,
        "diagnostic": diagnostic,
        "model": "state_by_state",
        "species": species_label,
        "window_nm": [float(window_nm[0]), float(window_nm[1])],
        "database_kind": "demo" if demo_database else "validated",
        "database_source": database_source_label,
        "transition_count": int(len(transitions)),
        "state_count": len(populations),
        "instrument_profile": instrument_profile,
        "fit_tvib": False,
        "parameters": parameters,
        "metrics": metrics,
        "fit_quality": classify_fit_quality(metrics, warnings),
        "warnings": warnings,
        "state_populations": populations,
        "boltzmann_by_v": boltzmann_by_v,
        "analysis_notes": [
            "State-by-state mode fits relative upper-state populations; Boltzmann temperatures are post-fit apparent slopes, not imposed fit parameters."
        ],
        "solver": {
            "outer_status": nonlinear_status,
            "outer_cost": nonlinear_cost,
            "linear_cost": float(final["cost"]),
            "fit_wavelength_shift": bool(fit_wavelength_shift),
            "fit_instrument_fwhm": bool(fit_instrument_fwhm),
        },
        "preprocessing_history": spectrum.preprocessing_history,
        "fit_curve": serializable_array_pair(x, y_fit),
        "measured_curve": serializable_array_pair(x, y),
        "residual_curve": serializable_array_pair(x, y - y_fit),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_transitions(
    species_id: str,
    window_nm: tuple[float, float] | list[float],
    explicit_path: str | Path | None,
    database_source: str,
    demo_csv: Path,
) -> tuple[pd.DataFrame, str, bool]:
    """Pick the transition source based on caller preference and disk availability.

    Returns ``(transitions, source_label, demo_database)``.
    """

    if explicit_path is not None:
        return load_transition_csv(explicit_path), f"csv:{Path(explicit_path).name}", True

    if database_source not in ("auto", "sqlite", "demo"):
        raise ValueError(f"unsupported database_source: {database_source!r}")

    if database_source != "demo" and molecular_store.has_species_db(species_id):
        try:
            transitions = molecular_store.load_species_transitions(
                species_id,
                window_nm=(float(window_nm[0]) - 2.0, float(window_nm[1]) + 2.0),
            )
        except Exception as exc:  # pragma: no cover - depends on db state
            if database_source == "sqlite":
                raise
            transitions = pd.DataFrame()
            sqlite_error: Exception | None = exc
        else:
            sqlite_error = None
        if not transitions.empty and sqlite_error is None:
            label = f"sqlite:{molecular_store.SPECIES_REGISTRY[species_id].db_filename}"
            return transitions, label, False

    if database_source == "sqlite":
        raise FileNotFoundError(
            f"requested SQLite database for {species_id!r} is unavailable; "
            "set PLASMA_SPEC_MOLECULAR_DB_DIR or place the file in "
            "'Molecular Line Data/'"
        )
    return load_transition_csv(demo_csv), f"csv:{demo_csv.name}", True


def load_transition_csv(path: str | Path) -> pd.DataFrame:
    """Load a transition CSV with wavelength, upper energy, and strength columns."""

    frame = pd.read_csv(path)
    required = {"wavelength_nm", "energy_upper_cm1", "strength"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"transition database missing required columns: {sorted(missing)}")
    return frame


# Back-compat alias for callers/tests that imported the old name.
load_transition_database = load_transition_csv


def _prepare_state_by_state_transitions(transitions: pd.DataFrame) -> pd.DataFrame:
    """Normalize transition columns used by the state-by-state solver."""

    frame = transitions.copy()
    frame["wavelength_nm"] = pd.to_numeric(frame["wavelength_nm"], errors="coerce")
    if "einstein_A" not in frame.columns:
        frame["einstein_A"] = np.nan
    frame["einstein_A"] = pd.to_numeric(frame["einstein_A"], errors="coerce")
    if "strength" in frame.columns:
        fallback_a = pd.to_numeric(frame["strength"], errors="coerce")
        j_source = frame["j_upper"] if "j_upper" in frame.columns else pd.Series(0.0, index=frame.index)
        degeneracy = 2.0 * pd.to_numeric(j_source, errors="coerce").fillna(0.0) + 1.0
        frame["einstein_A"] = frame["einstein_A"].fillna(fallback_a / degeneracy.replace(0, np.nan))
    frame["einstein_A"] = frame["einstein_A"].fillna(0.0)

    for column in ("j_upper", "v_upper", "v_lower", "e_rot_upper_cm1", "e_vib_upper_cm1"):
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "energy_upper_cm1" not in frame.columns:
        frame["energy_upper_cm1"] = frame["e_rot_upper_cm1"].fillna(0.0) + frame["e_vib_upper_cm1"].fillna(0.0)
    frame["energy_upper_cm1"] = pd.to_numeric(frame["energy_upper_cm1"], errors="coerce")
    if "upper_component" not in frame.columns:
        frame["upper_component"] = ""
    if "branch" not in frame.columns:
        frame["branch"] = ""

    finite = (
        np.isfinite(frame["wavelength_nm"].to_numpy(dtype=float))
        & np.isfinite(frame["einstein_A"].to_numpy(dtype=float))
        & (frame["wavelength_nm"].to_numpy(dtype=float) > 0)
        & (frame["einstein_A"].to_numpy(dtype=float) > 0)
    )
    frame = frame.loc[finite].copy()
    frame["_state_key"] = frame.apply(_state_key_for_row, axis=1)
    return frame


def _state_key_for_row(row: pd.Series) -> str:
    upper_id = row.get("upper_state_id")
    if pd.notna(upper_id):
        try:
            return f"upper:{int(float(upper_id))}"
        except (TypeError, ValueError):
            return f"upper:{upper_id}"
    return (
        f"v={_compact_number(row.get('v_upper'))};"
        f"J={_compact_number(row.get('j_upper'))};"
        f"Erot={_compact_number(row.get('e_rot_upper_cm1'))};"
        f"Evib={_compact_number(row.get('e_vib_upper_cm1'))};"
        f"comp={row.get('upper_component') or ''}"
    )


def _compact_number(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(numeric):
        return ""
    if abs(numeric - round(numeric)) < 1e-9:
        return str(int(round(numeric)))
    return f"{numeric:.6g}"


def _select_state_rows(
    transitions: pd.DataFrame,
    *,
    max_states: int,
    min_state_relative_strength: float,
) -> list[dict[str, Any]]:
    """Pick the strongest upper states in the window for a stable fit."""

    grouped = transitions.groupby("_state_key", sort=False)
    rows: list[dict[str, Any]] = []
    for state_key, group in grouped:
        total_a = float(group["einstein_A"].sum())
        if total_a <= 0:
            continue
        first = group.iloc[0]
        rows.append(
            {
                "state_key": str(state_key),
                "line_count": int(len(group)),
                "total_einstein_A": total_a,
                "v_upper": _float_or_none(first.get("v_upper")),
                "j_upper": _float_or_none(first.get("j_upper")),
                "v_lower_values": sorted(
                    {
                        int(value) if abs(float(value) - round(float(value))) < 1e-9 else float(value)
                        for value in group["v_lower"].dropna().tolist()
                    }
                ),
                "e_rot_upper_cm1": _float_or_none(first.get("e_rot_upper_cm1")),
                "e_vib_upper_cm1": _float_or_none(first.get("e_vib_upper_cm1")),
                "energy_upper_cm1": _float_or_none(first.get("energy_upper_cm1")),
                "upper_component": str(first.get("upper_component") or ""),
                "branches": sorted({str(value) for value in group["branch"].dropna().tolist()}),
            }
        )
    if not rows:
        return []
    rows.sort(key=lambda item: item["total_einstein_A"], reverse=True)
    strongest = float(rows[0]["total_einstein_A"])
    threshold = strongest * float(min_state_relative_strength)
    selected = [row for row in rows if row["total_einstein_A"] >= threshold][:max_states]
    selected.sort(
        key=lambda item: (
            float("inf") if item["v_upper"] is None else item["v_upper"],
            float("inf") if item["j_upper"] is None else item["j_upper"],
            item["state_key"],
        )
    )
    return selected


def _state_basis_matrix(
    x: np.ndarray,
    transitions: pd.DataFrame,
    state_rows: list[dict[str, Any]],
    *,
    wavelength_shift_nm: float,
    instrument_fwhm_nm: float,
    instrument_profile: InstrumentProfile,
    instrument_lorentz_fwhm_nm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Build normalized per-state basis spectra and their physical scales."""

    sigma = sigma_from_gaussian_fwhm(instrument_fwhm_nm)
    columns: list[np.ndarray] = []
    scales: list[float] = []
    for state in state_rows:
        group = transitions[transitions["_state_key"] == state["state_key"]]
        wavelengths = group["wavelength_nm"].to_numpy(dtype=float) + float(wavelength_shift_nm)
        weights = group["einstein_A"].to_numpy(dtype=float)
        if instrument_profile == "voigt" and instrument_lorentz_fwhm_nm > 0:
            raw = _accumulate_voigt(
                x,
                wavelengths,
                weights,
                sigma,
                float(instrument_lorentz_fwhm_nm) / 2.0,
            )
        else:
            raw = _accumulate_gaussian(x, wavelengths, weights, sigma)
        scale = float(np.max(np.abs(raw)))
        if not np.isfinite(scale) or scale <= 0:
            scale = 1.0
        columns.append(raw / scale)
        scales.append(scale)
    return np.column_stack(columns), np.asarray(scales, dtype=float)


def _state_population_rows(
    state_rows: list[dict[str, Any]],
    normalized_coefficients: np.ndarray,
    basis_scales: np.ndarray,
) -> list[dict[str, Any]]:
    """Convert fitted normalized coefficients to relative upper-state populations."""

    physical = np.asarray(normalized_coefficients, dtype=float) / np.asarray(basis_scales, dtype=float)
    physical = np.where(np.isfinite(physical) & (physical > 0), physical, 0.0)
    max_population = float(np.max(physical)) if physical.size else 0.0
    rows: list[dict[str, Any]] = []
    for state, coefficient, population in zip(state_rows, normalized_coefficients, physical, strict=True):
        degeneracy = None
        if state["j_upper"] is not None:
            degeneracy = 2.0 * float(state["j_upper"]) + 1.0
        relative = float(population / max_population) if max_population > 0 else 0.0
        boltzmann_y = None
        if population > 0 and degeneracy and degeneracy > 0:
            boltzmann_y = float(np.log(population / degeneracy))
        rows.append(
            {
                **state,
                "fit_coefficient": float(coefficient),
                "relative_population": relative,
                "population": float(population),
                "degeneracy": float(degeneracy) if degeneracy is not None else None,
                "ln_population_over_g": boltzmann_y,
            }
        )
    rows.sort(
        key=lambda item: (
            float("inf") if item["v_upper"] is None else item["v_upper"],
            float("inf") if item["j_upper"] is None else item["j_upper"],
            item["state_key"],
        )
    )
    return rows


def _boltzmann_summaries_by_v(populations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fit apparent Boltzmann slopes for each v' manifold after population fitting."""

    summaries: list[dict[str, Any]] = []
    v_values = sorted(
        {
            row["v_upper"]
            for row in populations
            if row.get("v_upper") is not None and row.get("ln_population_over_g") is not None
        }
    )
    for v_upper in v_values:
        rows = [
            row for row in populations
            if row.get("v_upper") == v_upper
            and row.get("ln_population_over_g") is not None
            and row.get("e_rot_upper_cm1") is not None
        ]
        if len(rows) < 3:
            continue
        x_energy = np.asarray([float(row["e_rot_upper_cm1"]) for row in rows], dtype=float)
        y_log = np.asarray([float(row["ln_population_over_g"]) for row in rows], dtype=float)
        weights = np.asarray([max(float(row["relative_population"]), 1e-6) for row in rows], dtype=float)
        try:
            slope, intercept = np.polyfit(x_energy, y_log, deg=1, w=np.sqrt(weights))
        except np.linalg.LinAlgError:
            continue
        y_pred = slope * x_energy + intercept
        ss_res = float(np.sum((y_log - y_pred) ** 2))
        ss_tot = float(np.sum((y_log - float(np.mean(y_log))) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        apparent_trot = -SECOND_RADIATION_CONSTANT_CM_K / float(slope) if slope < 0 else None
        summaries.append(
            {
                "v_upper": float(v_upper),
                "state_count": len(rows),
                "apparent_trot_K": float(apparent_trot) if apparent_trot is not None else None,
                "slope": float(slope),
                "intercept": float(intercept),
                "r2": float(r2),
            }
        )
    return summaries


def _state_by_state_warnings(
    *,
    metrics: dict[str, float],
    parameters: dict[str, Any],
    demo_database: bool,
    selected_count: int,
    available_state_count: int,
    max_states: int,
    shift_bounds: tuple[float, float],
) -> list[str]:
    warnings: list[str] = []
    if demo_database:
        warnings.append(DEMO_DATABASE_WARNING)
    if metrics.get("snr", 0.0) < 5:
        warnings.append("Weak molecular band signal or low SNR")
    if metrics.get("normalized_rmse", 0.0) > 0.15:
        warnings.append("High residual error")
    if available_state_count > selected_count and selected_count >= max_states:
        warnings.append(
            f"State-by-state fit used the strongest {selected_count} of {available_state_count} states; increase max_states for a fuller model."
        )
    shift = float(parameters.get("wavelength_shift_nm") or 0.0)
    shift_span = shift_bounds[1] - shift_bounds[0]
    if shift_span > 0 and abs(shift) > 0.5 * shift_span:
        warnings.append(
            f"Wavelength shift {shift:+.3f} nm is large; check spectrometer calibration"
        )
    return warnings


def _float_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def molecular_synthetic_spectrum(
    wavelength_grid_nm: np.ndarray,
    transitions: pd.DataFrame,
    trot_K: float,
    instrument_fwhm_nm: float,
    wavelength_shift_nm: float = 0.0,
    *,
    tvib_K: float | None = None,
    instrument_profile: InstrumentProfile = "gaussian",
    instrument_lorentz_fwhm_nm: float = 0.0,
) -> np.ndarray:
    """Generate a normalized molecular emission spectrum from transition rows.

    Per-line emission intensity follows

        I_line ~ strength * exp(-c2 * (E_rot - E_rot_min) / Trot)
                          * exp(-c2 * (E_vib - E_vib_min) / Tvib)

    where ``strength = A_ki * (2 J' + 1)`` is precomputed by the SQLite store
    and ``c2 = 1.4388 cm*K`` is the second radiation constant. Subtracting the
    minimum energy in each manifold is a numerical-conditioning trick - the
    absolute scale is folded into the ``scale`` fit parameter upstream.

    The two-temperature path requires the transitions DataFrame to carry
    separate ``e_rot_upper_cm1`` and ``e_vib_upper_cm1`` columns (provided by
    ``databases.molecular.store``). If those columns are absent (e.g. the old
    demo CSV with only ``energy_upper_cm1``) the function falls back to single
    temperature using ``trot_K`` on the combined energy.

    ``instrument_profile`` selects the per-line shape used to convolve the
    delta-function transitions to a continuous spectrum. Gaussian uses just
    ``instrument_fwhm_nm``; Voigt uses ``instrument_fwhm_nm`` as the Gaussian
    FWHM and ``instrument_lorentz_fwhm_nm`` as the Lorentzian FWHM.
    """

    x = np.asarray(wavelength_grid_nm, dtype=float)
    if transitions.empty:
        return np.zeros_like(x)

    strengths = transitions["strength"].to_numpy(dtype=float)
    wavelengths = transitions["wavelength_nm"].to_numpy(dtype=float) + float(wavelength_shift_nm)

    if (
        tvib_K is not None
        and "e_rot_upper_cm1" in transitions.columns
        and "e_vib_upper_cm1" in transitions.columns
    ):
        e_rot = transitions["e_rot_upper_cm1"].to_numpy(dtype=float)
        e_vib = transitions["e_vib_upper_cm1"].to_numpy(dtype=float)
        rot_factor = _boltzmann_factor(e_rot - float(np.min(e_rot)), trot_K)
        vib_factor = _boltzmann_factor(e_vib - float(np.min(e_vib)), float(tvib_K))
        intensities = strengths * rot_factor * vib_factor
    else:
        energies = transitions["energy_upper_cm1"].to_numpy(dtype=float)
        intensities = strengths * rotational_boltzmann_factor(
            energies - float(np.min(energies)), trot_K
        )

    if instrument_profile == "gaussian":
        sigma = sigma_from_gaussian_fwhm(instrument_fwhm_nm)
        model = _accumulate_gaussian(x, wavelengths, intensities, sigma)
    elif instrument_profile == "voigt":
        sigma = sigma_from_gaussian_fwhm(instrument_fwhm_nm)
        if instrument_lorentz_fwhm_nm <= 0:
            # Voigt collapses to Gaussian when gamma -> 0; degrade gracefully.
            model = _accumulate_gaussian(x, wavelengths, intensities, sigma)
        else:
            gamma = float(instrument_lorentz_fwhm_nm) / 2.0
            model = _accumulate_voigt(x, wavelengths, intensities, sigma, gamma)
    else:
        raise ValueError(f"unsupported instrument_profile: {instrument_profile!r}")

    area = np.trapezoid(model, x)
    if area > 0:
        model = model / area
    return model


def _boltzmann_factor(energy_cm1: np.ndarray, temperature_K: float) -> np.ndarray:
    """Per-line Boltzmann factor exp(-c2 * E / T) without partition functions."""

    if temperature_K <= 0:
        raise ValueError("temperature must be positive")
    return np.exp(-SECOND_RADIATION_CONSTANT_CM_K * energy_cm1 / float(temperature_K))


def _accumulate_gaussian(
    grid: np.ndarray, centers: np.ndarray, intensities: np.ndarray, sigma: float
) -> np.ndarray:
    """Sum a set of Gaussian profiles onto ``grid`` in batches to bound RAM."""

    model = np.zeros_like(grid)
    norm = 1.0 / (sigma * np.sqrt(2.0 * np.pi))
    batch = 512  # tuned to keep one batch under a few MB on float64
    for start in range(0, len(centers), batch):
        end = start + batch
        c = centers[start:end][:, None]  # (b, 1)
        w = intensities[start:end][:, None]
        z = (grid[None, :] - c) / sigma  # (b, n_grid)
        np.add.at(model, slice(None), np.sum(w * np.exp(-0.5 * z * z) * norm, axis=0))
    return model


def _accumulate_voigt(
    grid: np.ndarray,
    centers: np.ndarray,
    intensities: np.ndarray,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    """Sum a set of Voigt profiles using scipy.special.wofz, batched."""

    from scipy.special import wofz  # local import keeps cold-start cheap

    model = np.zeros_like(grid)
    norm = 1.0 / (sigma * np.sqrt(2.0 * np.pi))
    batch = 256
    for start in range(0, len(centers), batch):
        end = start + batch
        c = centers[start:end][:, None]
        w = intensities[start:end][:, None]
        z = ((grid[None, :] - c) + 1j * gamma) / (sigma * np.sqrt(2.0))
        model += np.sum(w * np.real(wofz(z)) * norm, axis=0)
    return model


def molecular_warnings(
    metrics: dict[str, float],
    params: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    demo_database: bool,
) -> list[str]:
    """Legacy warnings helper kept for back-compat with the old call sites."""

    warnings: list[str] = []
    if demo_database:
        warnings.append(DEMO_DATABASE_WARNING)
    if metrics["snr"] < 5:
        warnings.append("Weak molecular band signal or low SNR")
    if metrics["normalized_rmse"] > 0.15:
        warnings.append("High residual error")
    names = ["Trot", "scale", "wavelength_shift_nm", "instrument_fwhm_nm", "baseline_0", "baseline_1"]
    for name, value, lo, hi in zip(names, params, lower, upper, strict=True):
        if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
            if min(abs(value - lo), abs(hi - value)) / (hi - lo) < 0.02:
                warnings.append(f"Fit parameter hit boundary or is very close to boundary: {name}")
    shift_span = float(upper[2] - lower[2])
    if shift_span > 0 and abs(params[2]) > 0.5 * shift_span:
        warnings.append(
            f"Wavelength shift {params[2]:+.3f} nm is large; check spectrometer calibration"
        )
    if params[3] < 0.02 or params[3] > 1.5:
        warnings.append(
            f"Instrument FWHM {params[3]:.3f} nm is outside typical 0.02-1.5 nm range"
        )
    return warnings


# --- Phase 2 parameter-spec machinery ---------------------------------------

from dataclasses import dataclass


@dataclass(slots=True)
class _ParamEntry:
    name: str
    initial: float
    lower: float
    upper: float


def _build_param_spec(
    *,
    y: np.ndarray,
    initial_trot_K: float,
    trot_bounds_K: tuple[float, float] | list[float],
    fit_tvib: bool,
    initial_tvib_K: float | None,
    tvib_bounds_K: tuple[float, float] | list[float],
    wavelength_shift_nm: float,
    wavelength_shift_bounds_nm: tuple[float, float] | list[float],
    instrument_fwhm_nm: float,
    instrument_fwhm_bounds_nm: tuple[float, float] | list[float],
    instrument_profile: InstrumentProfile,
    instrument_lorentz_fwhm_nm: float,
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] | list[float],
    fit_instrument_lorentz: bool,
) -> list[_ParamEntry]:
    """Build the ordered parameter spec for ``least_squares``.

    Order matters: scipy returns ``fit.x`` and ``fit.jac`` indexed by this
    sequence. Optional parameters are appended only when enabled so the
    Jacobian stays well-conditioned.
    """

    trot_lo, trot_hi = float(trot_bounds_K[0]), float(trot_bounds_K[1])
    if trot_lo >= trot_hi:
        raise ValueError("trot_bounds_K must be ordered low < high")

    shift_lo, shift_hi = float(wavelength_shift_bounds_nm[0]), float(wavelength_shift_bounds_nm[1])
    fwhm_lo, fwhm_hi = float(instrument_fwhm_bounds_nm[0]), float(instrument_fwhm_bounds_nm[1])
    if shift_lo >= shift_hi or fwhm_lo >= fwhm_hi:
        raise ValueError("shift / instrument FWHM bounds must be ordered low < high")

    spec: list[_ParamEntry] = []
    spec.append(
        _ParamEntry(
            "trot_K",
            float(np.clip(initial_trot_K, trot_lo, trot_hi)),
            trot_lo,
            trot_hi,
        )
    )
    if fit_tvib:
        tvib_lo, tvib_hi = float(tvib_bounds_K[0]), float(tvib_bounds_K[1])
        if tvib_lo >= tvib_hi:
            raise ValueError("tvib_bounds_K must be ordered low < high")
        if initial_tvib_K is None:
            initial_tvib_K = initial_trot_K
        spec.append(
            _ParamEntry(
                "tvib_K",
                float(np.clip(initial_tvib_K, tvib_lo, tvib_hi)),
                tvib_lo,
                tvib_hi,
            )
        )

    scale0 = max(float(np.ptp(y)), 1e-12)
    b0 = float(np.percentile(y, 10))
    spec.append(_ParamEntry("scale", scale0, 0.0, float(np.inf)))
    spec.append(
        _ParamEntry(
            "wavelength_shift_nm",
            float(np.clip(wavelength_shift_nm, shift_lo, shift_hi)),
            shift_lo,
            shift_hi,
        )
    )
    spec.append(
        _ParamEntry(
            "instrument_fwhm_nm",
            float(np.clip(instrument_fwhm_nm, fwhm_lo, fwhm_hi)),
            fwhm_lo,
            fwhm_hi,
        )
    )
    if instrument_profile == "voigt" and fit_instrument_lorentz:
        lorentz_lo, lorentz_hi = (
            float(instrument_lorentz_fwhm_bounds_nm[0]),
            float(instrument_lorentz_fwhm_bounds_nm[1]),
        )
        if lorentz_lo >= lorentz_hi:
            raise ValueError("instrument_lorentz_fwhm_bounds_nm must be ordered low < high")
        spec.append(
            _ParamEntry(
                "instrument_lorentz_fwhm_nm",
                float(np.clip(instrument_lorentz_fwhm_nm, lorentz_lo, lorentz_hi)),
                lorentz_lo,
                lorentz_hi,
            )
        )
    spec.append(_ParamEntry("baseline_0", b0, -np.inf, np.inf))
    spec.append(_ParamEntry("baseline_1", 0.0, -np.inf, np.inf))
    return spec


def _unpack(vector: np.ndarray, spec: list[_ParamEntry]) -> dict[str, float]:
    return {entry.name: float(value) for entry, value in zip(spec, vector, strict=True)}


def _override_trot_initial(spec: list[_ParamEntry], trot: float) -> list[_ParamEntry]:
    """Return a copy of ``spec`` with the trot_K initial value overridden."""

    return [
        _ParamEntry(
            entry.name,
            float(np.clip(trot, entry.lower, entry.upper)) if entry.name == "trot_K" else entry.initial,
            entry.lower,
            entry.upper,
        )
        for entry in spec
    ]


def _parameter_stderr_from_jac(fit, spec: list[_ParamEntry]) -> dict[str, float | None]:
    """Standard error per parameter from the Jacobian, scaled by residual variance.

    Mirrors what ``scipy.optimize.curve_fit`` does internally:
    ``cov = (J^T J)^{-1} * residual_variance`` where the variance estimate is
    ``2 * cost / (n_data - n_params)``.
    """

    try:
        n_data = fit.fun.size
        n_params = fit.x.size
        if n_data <= n_params:
            return {entry.name: None for entry in spec}
        residual_var = 2.0 * float(fit.cost) / float(n_data - n_params)
        jac = fit.jac
        # least_squares may return a sparse jac; densify for safety.
        if hasattr(jac, "toarray"):
            jac = jac.toarray()
        cov = np.linalg.pinv(jac.T @ jac) * residual_var
        diag = np.diag(cov)
        return {
            entry.name: (float(np.sqrt(value)) if value >= 0 and np.isfinite(value) else None)
            for entry, value in zip(spec, diag, strict=True)
        }
    except Exception:  # pragma: no cover - covariance can fail for stiff fits
        return {entry.name: None for entry in spec}


def _instrument_profile_info(
    profile: InstrumentProfile,
    params: dict[str, float],
    fixed_lorentz_fwhm_nm: float,
) -> dict[str, float | None]:
    gauss_fwhm = float(params["instrument_fwhm_nm"])
    if profile == "voigt":
        lorentz_fwhm = float(params.get("instrument_lorentz_fwhm_nm", fixed_lorentz_fwhm_nm))
        sigma = sigma_from_gaussian_fwhm(gauss_fwhm)
        gamma = max(lorentz_fwhm, 1e-12) / 2.0
        total = voigt_fwhm(sigma, gamma)
        return {
            "gaussian_fwhm_nm": gauss_fwhm,
            "lorentzian_fwhm_nm": lorentz_fwhm,
            "total_fwhm_nm": float(total),
        }
    return {
        "gaussian_fwhm_nm": gauss_fwhm,
        "lorentzian_fwhm_nm": None,
        "total_fwhm_nm": gauss_fwhm,
    }


def molecular_warnings_v2(
    metrics: dict[str, float],
    params: dict[str, float],
    spec: list[_ParamEntry],
    demo_database: bool,
) -> list[str]:
    """User-facing warnings for the Phase 2 molecular fit."""

    warnings: list[str] = []
    if demo_database:
        warnings.append(DEMO_DATABASE_WARNING)
    if metrics.get("snr", 0.0) < 5:
        warnings.append("Weak molecular band signal or low SNR")
    if metrics.get("normalized_rmse", 0.0) > 0.15:
        warnings.append("High residual error")

    for entry in spec:
        value = params.get(entry.name)
        if value is None or not np.isfinite(entry.lower) or not np.isfinite(entry.upper):
            continue
        span = entry.upper - entry.lower
        if span <= 0:
            continue
        if min(abs(value - entry.lower), abs(entry.upper - value)) / span < 0.02:
            warnings.append(f"Fit parameter hit boundary or is very close to boundary: {entry.name}")

    shift_entry = next((e for e in spec if e.name == "wavelength_shift_nm"), None)
    if shift_entry is not None:
        span = shift_entry.upper - shift_entry.lower
        shift = params.get("wavelength_shift_nm", 0.0)
        if span > 0 and abs(shift) > 0.5 * span:
            warnings.append(
                f"Wavelength shift {shift:+.3f} nm is large; check spectrometer calibration"
            )

    fwhm = params.get("instrument_fwhm_nm")
    if fwhm is not None and (fwhm < 0.02 or fwhm > 1.5):
        warnings.append(
            f"Instrument FWHM {fwhm:.3f} nm is outside typical 0.02-1.5 nm range"
        )

    return warnings
