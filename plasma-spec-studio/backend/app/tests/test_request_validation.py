from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.analysis.electron_density.orchestrator import compute_electron_density
from app.core.spectrum import Spectrum
from app.schemas.fitting_schema import (
    ElectronDensityRequest,
    MolecularFitRequest,
    PeakListEntry,
    PeakListRequest,
    StateByStateMolecularFitRequest,
)


def test_electron_density_request_rejects_unphysical_values():
    with pytest.raises(ValidationError):
        ElectronDensityRequest(spectrum_id="s1", Tg_K=-1)

    with pytest.raises(ValidationError):
        ElectronDensityRequest(spectrum_id="s1", Tg_K=650, instrument_gauss_fwhm_nm=0)

    with pytest.raises(ValidationError):
        ElectronDensityRequest(spectrum_id="s1", Tg_K=650, intensity_threshold_rel=1.2)

    with pytest.raises(ValidationError):
        ElectronDensityRequest(spectrum_id="s1", Tg_K=650, window_nm=(700, 600))


def test_peak_list_request_rejects_nonpositive_windows():
    with pytest.raises(ValidationError):
        PeakListEntry(center_nm=656.279, half_width_nm=0)

    with pytest.raises(ValidationError):
        PeakListRequest(
            spectrum_id="s1",
            peaks=[PeakListEntry(center_nm=656.279)],
            default_half_width_nm=-0.5,
        )


def test_molecular_request_rejects_bad_bounds_and_restart_temperatures():
    with pytest.raises(ValidationError):
        MolecularFitRequest(spectrum_id="s1", window_nm=(312, 306))

    with pytest.raises(ValidationError):
        MolecularFitRequest(
            spectrum_id="s1",
            window_nm=(306, 312),
            instrument_fwhm_nm=-0.1,
        )

    with pytest.raises(ValidationError):
        MolecularFitRequest(
            spectrum_id="s1",
            window_nm=(306, 312),
            multi_restart_trot_K=[500, 0, 3500],
        )


def test_state_by_state_request_rejects_invalid_state_controls():
    with pytest.raises(ValidationError):
        StateByStateMolecularFitRequest(
            spectrum_id="s1",
            species_id="OH_AX",
            window_nm=(312, 306),
        )

    with pytest.raises(ValidationError):
        StateByStateMolecularFitRequest(
            spectrum_id="s1",
            species_id="OH_AX",
            window_nm=(306, 312),
            max_states=0,
        )

    with pytest.raises(ValidationError):
        StateByStateMolecularFitRequest(
            spectrum_id="s1",
            species_id="OH_AX",
            window_nm=(306, 312),
            min_state_relative_strength=1.0,
        )


def test_electron_density_core_rejects_recipe_bypass_values():
    spectrum = Spectrum(
        "dummy.csv",
        np.linspace(650.0, 660.0, 20),
        np.ones(20),
    )

    with pytest.raises(ValueError, match="instrument_gauss_fwhm_nm"):
        compute_electron_density(
            spectrum,
            Tg_K=650,
            instrument_gauss_fwhm_nm=0,
            intensity_threshold_rel=0.05,
        )

    with pytest.raises(ValueError, match="intensity_threshold_rel"):
        compute_electron_density(
            spectrum,
            Tg_K=650,
            instrument_gauss_fwhm_nm=0.13,
            intensity_threshold_rel=1.0,
        )
