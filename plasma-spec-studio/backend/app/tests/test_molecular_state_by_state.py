"""State-by-state molecular fitting tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.line_shapes import sigma_from_gaussian_fwhm
from app.core.spectrum import Spectrum
from app.models.boltzmann import SECOND_RADIATION_CONSTANT_CM_K
from app.models.molecular_band_model import (
    _accumulate_gaussian,
    fit_molecular_state_by_state,
)


def _synthetic_state_by_state_spectrum(trot_K: float = 1800.0) -> tuple[Spectrum, pd.DataFrame]:
    x = np.linspace(300.0, 304.0, 801)
    rows: list[dict[str, float | int | str]] = []
    y = 0.5 + 0.02 * (x - float(np.mean(x)))
    sigma = sigma_from_gaussian_fwhm(0.08)
    for index, j_upper in enumerate([4, 5, 6, 7, 8], start=1):
        e_rot = 90.0 * j_upper * (j_upper + 1.0)
        degeneracy = 2.0 * j_upper + 1.0
        population = 200.0 * degeneracy * np.exp(
            -SECOND_RADIATION_CONSTANT_CM_K * e_rot / trot_K
        )
        centers = np.array([300.25 + index * 0.58, 300.31 + index * 0.58])
        einstein = np.array([1.0, 0.55])
        y += population * _accumulate_gaussian(x, centers, einstein, sigma)
        for line_index, (center, a_value) in enumerate(zip(centers, einstein, strict=True)):
            rows.append(
                {
                    "upper_state_id": index,
                    "wavelength_nm": float(center),
                    "einstein_A": float(a_value),
                    "branch": "P" if line_index == 0 else "Q",
                    "e_rot_upper_cm1": float(e_rot),
                    "e_vib_upper_cm1": 0.0,
                    "energy_upper_cm1": float(e_rot),
                    "j_upper": float(j_upper),
                    "v_upper": 0.0,
                    "v_lower": 0.0,
                    "upper_component": "",
                    "strength": float(a_value * degeneracy),
                }
            )
    return Spectrum("state_by_state.csv", x, y), pd.DataFrame(rows)


def test_state_by_state_fit_recovers_population_spectrum_and_boltzmann_slope():
    spectrum, transitions = _synthetic_state_by_state_spectrum(trot_K=1800.0)

    result = fit_molecular_state_by_state(
        spectrum=spectrum,
        species_label="Synthetic",
        diagnostic="molecular_state_synthetic",
        window_nm=(300.0, 304.0),
        transitions=transitions,
        instrument_fwhm_nm=0.08,
        wavelength_shift_nm=0.0,
        demo_database=False,
        database_source_label="synthetic",
        max_states=10,
        fit_wavelength_shift=False,
        fit_instrument_fwhm=False,
    )

    assert result["model"] == "state_by_state"
    assert result["state_count"] == 5
    assert result["metrics"]["r2"] > 0.999
    assert len(result["state_populations"]) == 5
    assert result["boltzmann_by_v"]
    apparent_trot = result["boltzmann_by_v"][0]["apparent_trot_K"]
    assert apparent_trot is not None
    assert abs(apparent_trot - 1800.0) < 75.0
