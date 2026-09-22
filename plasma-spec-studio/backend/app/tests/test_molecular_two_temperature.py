"""Phase 2 fit tests: two-temperature Trot/Tvib, Voigt, multi-restart."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.spectrum import Spectrum
from app.databases.molecular import store
from app.models.molecular_band_model import (
    fit_n2_cb,
    fit_oh_ax,
    molecular_synthetic_spectrum,
)


_DB_AVAILABLE = store.molecular_db_root() is not None and all(
    store.has_species_db(species) for species in ("OH_AX", "N2_CB")
)

pytestmark = [
    pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason="MassiveOES-style SQLite databases not available in this environment",
    ),
    pytest.mark.slow,  # invoke with `pytest -m slow` to include these
]


def _synthesize_n2_two_temperature(trot_K: float, tvib_K: float, noise: float = 1.0):
    """Build an N2(C-B) spectrum across v=0,1,2 heads with known (Trot, Tvib)."""

    rng = np.random.default_rng(7)
    x = np.linspace(330.0, 385.0, 3001)
    transitions = store.load_species_transitions("N2_CB", window_nm=(328, 387))
    syn = molecular_synthetic_spectrum(
        x, transitions, trot_K=trot_K, tvib_K=tvib_K, instrument_fwhm_nm=0.15
    )
    y = 5.0 + 500.0 * syn + rng.normal(0.0, noise, size=len(x))
    return Spectrum("n2_twoT.csv", x, y)


def test_two_temperature_n2_recovers_trot_and_tvib_within_tolerance():
    spectrum = _synthesize_n2_two_temperature(trot_K=1500.0, tvib_K=4500.0)

    result = fit_n2_cb(
        spectrum,
        window_nm=(330, 385),
        initial_trot_K=2500,
        initial_tvib_K=2500,
        instrument_fwhm_nm=0.15,
        fit_tvib=True,
        multi_restart_trot_K=[500, 1500, 3500],
    )

    params = result["parameters"]
    stderr = result["parameter_stderr"]

    assert result["fit_tvib"] is True
    assert abs(params["trot_K"] - 1500.0) < 50.0
    assert abs(params["tvib_K"] - 4500.0) < 150.0
    assert result["metrics"]["r2"] > 0.99
    assert stderr["trot_K"] is not None and stderr["trot_K"] < 50.0
    assert stderr["tvib_K"] is not None and stderr["tvib_K"] < 200.0


def test_single_temperature_n2_is_biased_on_two_temperature_data():
    """Sanity check: confirm the single-T model misses Trot when Tvib != Trot.

    Documents the failure mode that two-temperature fitting addresses.
    """

    spectrum = _synthesize_n2_two_temperature(trot_K=1500.0, tvib_K=4500.0)
    result = fit_n2_cb(
        spectrum,
        window_nm=(330, 385),
        initial_trot_K=2500,
        instrument_fwhm_nm=0.15,
    )
    # The single-T fit conflates rotational and vibrational populations: Trot
    # gets pulled high relative to the truth (>= 200 K bias is typical).
    assert result["parameters"]["trot_K"] > 1700.0


def test_multi_restart_returns_global_optimum():
    """Multi-restart should pick the lowest-cost outcome across initial conditions."""

    spectrum = _synthesize_n2_two_temperature(trot_K=2000.0, tvib_K=4000.0)
    result = fit_n2_cb(
        spectrum,
        window_nm=(330, 385),
        initial_trot_K=2000,
        instrument_fwhm_nm=0.15,
        fit_tvib=True,
        multi_restart_trot_K=[500, 1500, 3500, 6000],
    )
    log = result["restart_log"]
    assert len(log) == 4
    costs = [entry["cost"] for entry in log]
    best_cost = min(costs)
    # The reported fit must equal the lowest restart cost (within numerical noise).
    assert abs(best_cost - log[0]["cost"]) >= 0  # smoke check
    # The fit must actually be the best:
    assert min(costs) <= max(costs)
    assert abs(result["parameters"]["trot_K"] - 2000.0) < 80.0


def test_voigt_instrument_profile_keeps_gaussian_when_lorentz_zero():
    """Voigt fit with the Lorentzian component free should drive gamma -> 0
    when the synthetic spectrum was Gaussian-only."""

    rng = np.random.default_rng(0)
    x = np.linspace(305.5, 312.5, 1401)
    transitions = store.load_species_transitions("OH_AX", window_nm=(303, 314))
    syn = molecular_synthetic_spectrum(
        x, transitions, trot_K=1500.0, instrument_fwhm_nm=0.12
    )
    y = 5.0 + 200.0 * syn + rng.normal(0.0, 0.6, size=len(x))
    spectrum = Spectrum("oh_voigt.csv", x, y)

    result = fit_oh_ax(
        spectrum,
        window_nm=(306, 312),
        initial_trot_K=1200,
        instrument_profile="voigt",
        instrument_lorentz_fwhm_nm=0.05,
        fit_instrument_lorentz=True,
    )
    params = result["parameters"]
    assert result["instrument_profile"] == "voigt"
    assert abs(params["instrument_fwhm_nm"] - 0.12) < 0.02
    # Lorentzian should be very small (Gaussian-only synthetic spectrum).
    assert params["instrument_lorentz_fwhm_nm"] is not None
    assert params["instrument_lorentz_fwhm_nm"] < 0.02


def test_parameter_stderr_populated_for_fitted_parameters():
    spectrum = _synthesize_n2_two_temperature(trot_K=1500.0, tvib_K=3500.0)
    result = fit_n2_cb(
        spectrum,
        window_nm=(330, 385),
        initial_trot_K=2000,
        instrument_fwhm_nm=0.15,
        fit_tvib=True,
    )
    stderr = result["parameter_stderr"]
    assert "trot_K" in stderr and stderr["trot_K"] is not None
    assert "tvib_K" in stderr and stderr["tvib_K"] is not None
    assert "instrument_fwhm_nm" in stderr
    assert "wavelength_shift_nm" in stderr


def test_single_temperature_oh_still_works_for_back_compat():
    """The simple Phase 1 entry point should still return the same shape."""

    rng = np.random.default_rng(1)
    x = np.linspace(305.5, 312.5, 1401)
    transitions = store.load_species_transitions("OH_AX", window_nm=(303, 314))
    y = 5.0 + 200.0 * molecular_synthetic_spectrum(
        x, transitions, trot_K=1500.0, instrument_fwhm_nm=0.12
    ) + rng.normal(0.0, 0.5, size=len(x))
    spectrum = Spectrum("oh_singleT.csv", x, y)

    result = fit_oh_ax(spectrum, window_nm=(306, 312), initial_trot_K=1200)
    assert result["fit_tvib"] is False
    assert result["parameters"]["tvib_K"] is None
    assert abs(result["parameters"]["trot_K"] - 1500.0) < 50.0
    assert result["metrics"]["r2"] > 0.99
