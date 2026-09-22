"""Phase 4 batch tests: peak_list, electron_density, long-form export, recipe round-trip."""

from __future__ import annotations

import csv

import numpy as np
import pytest

from app.core.line_shapes import voigt
from app.core.spectrum import Spectrum
from app.services.batch_service import run_batch
from app.services.recipe_service import get_recipe, save_recipe
from app.services.spectrum_service import save_spectrum


# --- Peak-list batch -------------------------------------------------------


def _store_three_peak_spectrum(name: str, seed: int = 0) -> Spectrum:
    rng = np.random.default_rng(seed)
    x = np.linspace(300.0, 800.0, 8001)
    y = 5.0 + 0.0
    centers = [310.0, 486.135, 656.279]
    amps = [180.0, 140.0, 220.0]
    sigmas = [0.08, 0.05, 0.06]
    gammas = [0.04, 0.03, 0.04]
    for c, a, s, g in zip(centers, amps, sigmas, gammas):
        y = y + a * voigt(x, c, s, g)
    y = y + rng.normal(0.0, 0.1, size=len(x))
    return save_spectrum(Spectrum(name, x, y, metadata={"freq_khz": seed + 100}))


def test_peak_list_batch_produces_long_form_rows():
    spectra = [_store_three_peak_spectrum(f"peak_list_{i}.csv", seed=i) for i in range(3)]
    recipe = {
        "name": "OH+Hbeta+Halpha",
        "diagnostic": "peak_list",
        "recipe_kind": "peak_list",
        "preprocessing": [],
        "peak_list": {
            "peaks": [
                {"label": "OH-like", "center_nm": 310.0, "half_width_nm": 1.0, "fit_model": "voigt"},
                {"label": "Hbeta", "center_nm": 486.135, "half_width_nm": 1.0, "fit_model": "voigt"},
                {"label": "Halpha", "center_nm": 656.279, "half_width_nm": 1.0},  # data only
            ],
            "default_half_width_nm": 0.5,
        },
    }
    result = run_batch([s.id for s in spectra], recipe)
    assert result["completed"] == 3
    assert result["failed"] == 0
    assert len(result["rows"]) == 9  # 3 peaks * 3 spectra (long-form)
    labels = {row["peak_label"] for row in result["rows"]}
    assert labels == {"OH-like", "Hbeta", "Halpha"}
    # metadata flows through with the metadata_* prefix
    assert any("metadata_freq_khz" in row for row in result["rows"])
    # CSV + XLSX exports both written
    assert "csv" in result["exports"] and "xlsx" in result["exports"]


# --- Electron density batch -----------------------------------------------


def _store_halpha_spectrum(name: str, wL_nm: float, seed: int) -> Spectrum:
    rng = np.random.default_rng(seed)
    x = np.linspace(600.0, 700.0, 4001)
    profile = voigt(x, 656.279, sigma=0.055, gamma=wL_nm / 2.0)
    profile = profile / profile.max()
    y = 5.0 + 1000.0 * profile + rng.normal(0.0, 0.5, size=len(x))
    return save_spectrum(Spectrum(name, x, y, metadata={"label": name}))


def test_electron_density_batch_across_three_spectra():
    targets = [(0.30, 1), (0.50, 2), (0.80, 3)]
    spectra = [_store_halpha_spectrum(f"ne_{i}.csv", wL, seed=i) for i, (wL, _) in enumerate(targets)]
    recipe = {
        "name": "n_e batch",
        "diagnostic": "electron_density",
        "recipe_kind": "electron_density",
        "preprocessing": [],
        "electron_density": {
            "Tg_K": 650.0,
            "instrument_gauss_fwhm_nm": 0.13,
            "line": "halpha",
            "model": "single_voigt",
            "intensity_threshold_rel": 0.0,  # tight math path
        },
    }
    result = run_batch([s.id for s in spectra], recipe)
    assert result["completed"] == 3
    assert result["failed"] == 0
    assert len(result["rows"]) == 3
    for row, (wL_truth, _) in zip(result["rows"], targets):
        assert row["recipe_kind"] == "electron_density"
        assert row["lorentz_fwhm_nm"] is not None
        assert row["electron_density_cm3"] is not None
        # Widths recover within ~10% on clean synthetics.
        assert abs(row["lorentz_fwhm_nm"] - wL_truth) / wL_truth < 0.10


# --- Recipe round-trip for the new kinds ----------------------------------


@pytest.mark.parametrize(
    "recipe",
    [
        {
            "name": "peak list recipe",
            "diagnostic": "peak_list",
            "recipe_kind": "peak_list",
            "peak_list": {
                "peaks": [{"label": "Ar 750", "center_nm": 750.39, "half_width_nm": 1.0}],
            },
        },
        {
            "name": "molecular_v2 recipe",
            "diagnostic": "molecular_v2",
            "recipe_kind": "molecular_v2",
            "molecular": {"species_id": "OH_AX", "fit_tvib": True, "initial_trot_K": 1500},
        },
        {
            "name": "electron density recipe",
            "diagnostic": "electron_density",
            "recipe_kind": "electron_density",
            "electron_density": {"Tg_K": 650.0, "instrument_gauss_fwhm_nm": 0.13},
        },
    ],
)
def test_recipe_round_trip_preserves_new_param_blocks(recipe):
    saved = save_recipe(recipe)
    loaded = get_recipe(saved["id"])
    assert loaded["recipe_kind"] == recipe["recipe_kind"]
    # The new typed param block survives the round trip intact.
    block_key = {
        "peak_list": "peak_list",
        "molecular_v2": "molecular",
        "electron_density": "electron_density",
    }[recipe["recipe_kind"]]
    assert loaded[block_key] == recipe[block_key]


# --- Legacy recipe still works -------------------------------------------


def test_legacy_diagnostic_without_recipe_kind_still_dispatches():
    """Recipes saved before Phase 4 should keep running."""

    spectrum = save_spectrum(Spectrum("legacy.csv", np.linspace(484, 488, 401), 4 + 40 * voigt(np.linspace(484, 488, 401), 486.13, 0.06, 0.04)))
    recipe = {
        "name": "Hbeta legacy",
        "diagnostic": "hbeta_voigt",  # NOT recipe_kind
        "preprocessing": [],
        "window_nm": [484, 488],
        "fit_model": "voigt",
        "fit_parameters": {
            "center_bounds": [485.8, 486.4],
            "sigma_bounds": [0.001, 1.0],
            "gamma_bounds": [0.001, 1.0],
        },
    }
    result = run_batch([spectrum.id], recipe)
    assert result["completed"] == 1
    assert result["failed"] == 0
    assert result["recipe_kind"] == "hbeta_voigt"
    # The legacy result row should still have a usable summary.
    row = result["rows"][0]
    assert row.get("fit_quality") in {"good", "warning", "bad"}


# --- CSV + XLSX export sanity --------------------------------------------


def test_batch_writes_readable_csv_and_xlsx():
    from pathlib import Path

    spectra = [_store_three_peak_spectrum(f"export_{i}.csv", seed=i) for i in range(2)]
    recipe = {
        "name": "export-check",
        "diagnostic": "peak_list",
        "recipe_kind": "peak_list",
        "peak_list": {
            "peaks": [{"label": "Hbeta", "center_nm": 486.135, "half_width_nm": 1.0}],
        },
    }
    result = run_batch([s.id for s in spectra], recipe)
    csv_path = Path(result["exports"]["csv"]["path"])
    xlsx_path = Path(result["exports"]["xlsx"]["path"])
    assert csv_path.exists() and csv_path.stat().st_size > 0
    assert xlsx_path.exists() and xlsx_path.stat().st_size > 0
    # CSV should have one header + 2 rows
    with csv_path.open() as fp:
        lines = list(csv.reader(fp))
    assert len(lines) >= 3
    assert "peak_label" in lines[0]
