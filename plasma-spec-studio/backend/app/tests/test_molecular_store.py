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


pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="MassiveOES-style SQLite databases not available in this environment",
)


def test_species_registry_summarizes_available_databases():
    summary = {entry["id"]: entry for entry in store.list_species()}
    assert summary["OH_AX"]["available"] is True
    assert summary["OH_AX"]["line_count"] > 1000
    assert summary["N2_CB"]["available"] is True
    assert summary["N2_CB"]["line_count"] > 100_000
    assert summary["OH_AX"]["wavelength_min_nm"] < 290
    assert summary["OH_AX"]["wavelength_max_nm"] > 350


def test_load_oh_transitions_has_expected_columns_and_strength_weighting():
    frame = store.load_species_transitions("OH_AX", window_nm=(306.0, 312.0))
    assert not frame.empty
    expected_columns = {
        "wavelength_nm",
        "einstein_A",
        "branch",
        "j_upper",
        "v_upper",
        "v_lower",
        "energy_upper_cm1",
        "strength",
    }
    assert expected_columns.issubset(set(frame.columns))
    # Strength must equal A * (2J' + 1) per row.
    expected = frame["einstein_A"] * (2.0 * frame["j_upper"] + 1.0)
    assert np.allclose(frame["strength"], expected, equal_nan=True)
    # Energies must be non-negative cm^-1 and finite.
    assert (frame["energy_upper_cm1"] >= 0).all()


def test_oh_fit_recovers_synthetic_trot_from_real_database():
    rng = np.random.default_rng(0)
    x = np.linspace(305.5, 312.5, 1401)
    transitions = store.load_species_transitions("OH_AX", window_nm=(303.5, 314.5))
    synthetic = molecular_synthetic_spectrum(
        x,
        transitions,
        trot_K=1500.0,
        instrument_fwhm_nm=0.12,
        wavelength_shift_nm=0.0,
    )
    y = 5.0 + 200.0 * synthetic + rng.normal(0.0, 0.6, size=len(x))
    spectrum = Spectrum("oh_synth.csv", x, y)

    result = fit_oh_ax(spectrum, window_nm=(306.0, 312.0), initial_trot_K=1200.0)
    assert result["database_kind"] == "validated"
    assert result["database_source"].startswith("sqlite:")
    assert result["metrics"]["r2"] > 0.99
    assert abs(result["parameters"]["trot_K"] - 1500.0) < 50.0


def test_n2_fit_recovers_synthetic_trot_from_real_database():
    rng = np.random.default_rng(1)
    x = np.linspace(333.5, 339.5, 1201)
    transitions = store.load_species_transitions("N2_CB", window_nm=(331.5, 341.5))
    synthetic = molecular_synthetic_spectrum(
        x,
        transitions,
        trot_K=2000.0,
        instrument_fwhm_nm=0.12,
        wavelength_shift_nm=0.0,
    )
    y = 5.0 + 300.0 * synthetic + rng.normal(0.0, 0.7, size=len(x))
    spectrum = Spectrum("n2_synth.csv", x, y)

    result = fit_n2_cb(spectrum, window_nm=(334.0, 339.0), initial_trot_K=1500.0)
    assert result["database_kind"] == "validated"
    assert result["database_source"].startswith("sqlite:")
    assert result["metrics"]["r2"] > 0.99
    assert abs(result["parameters"]["trot_K"] - 2000.0) < 80.0
