"""Recipe schemas.

Phase 4 introduces ``recipe_kind`` as a discriminator that drives which
analysis the batch runner invokes. The original ``diagnostic`` field is kept
for back-compat: when ``recipe_kind`` is missing, batch infers the kind from
``diagnostic`` (so existing saved recipes keep working).

Recipe kinds (and the parameter block each one carries):

- ``peak_list`` -> ``peak_list`` (list of {label, center_nm, half_width_nm, fit_model})
- ``molecular_v2`` -> ``molecular`` (species_id, fit_tvib, multi_restart_trot_K, ...)
- ``electron_density`` -> ``electron_density`` (Tg_K, instrument_gauss_fwhm_nm, line, model, ...)
- ``hbeta_voigt`` / ``oh_ax`` / ``n2_cb`` / ``peak_area`` / ``line_identification``
  remain available through the original ``fit_parameters`` dict.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RecipeKind = Literal[
    "peak_list",
    "molecular_v2",
    "electron_density",
    "hbeta_voigt",
    "peak_area",
    "oh_ax",
    "n2_cb",
    "line_identification",
]


class PeakListPeak(BaseModel):
    label: str | None = None
    center_nm: float
    half_width_nm: float | None = None
    fit_model: Literal["gaussian", "lorentzian", "voigt"] | None = None
    species: str | None = None
    transition: str | None = None
    notes: str | None = None


class PeakListParams(BaseModel):
    peaks: list[PeakListPeak]
    default_half_width_nm: float = 0.5
    default_fit_model: Literal["gaussian", "lorentzian", "voigt"] | None = None


class MolecularParams(BaseModel):
    species_id: Literal["OH_AX", "N2_CB", "N2plus_BX", "NH_AX", "NO_BX"]
    fit_mode: Literal["boltzmann", "state_by_state"] = "boltzmann"
    window_nm: tuple[float, float] | None = None
    initial_trot_K: float = 1500.0
    initial_tvib_K: float | None = None
    trot_bounds_K: tuple[float, float] = (250.0, 6000.0)
    tvib_bounds_K: tuple[float, float] = (250.0, 10_000.0)
    instrument_fwhm_nm: float = 0.15
    wavelength_shift_nm: float = 0.0
    wavelength_shift_bounds_nm: tuple[float, float] = (-2.0, 2.0)
    instrument_fwhm_bounds_nm: tuple[float, float] = (0.01, 2.0)
    fit_tvib: bool = False
    instrument_profile: Literal["gaussian", "voigt"] = "gaussian"
    instrument_lorentz_fwhm_nm: float = 0.0
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] = (0.0, 1.0)
    fit_instrument_lorentz: bool = False
    multi_restart_trot_K: list[float] | None = None
    database_source: Literal["auto", "sqlite", "demo"] = "auto"
    max_states: int = 40
    min_state_relative_strength: float = 0.0
    fit_wavelength_shift: bool = True
    fit_instrument_fwhm: bool = True


class ElectronDensityParams(BaseModel):
    Tg_K: float
    instrument_gauss_fwhm_nm: float = 0.13
    line: Literal["halpha", "hbeta"] = "halpha"
    model: Literal["single_voigt", "two_voigt"] = "single_voigt"
    window_nm: tuple[float, float] | None = None
    intensity_threshold_rel: float = 0.05
    center_initial_nm: float | None = None
    lorentz_initial_nm: float = 1.0
    lorentz2_initial_nm: float = 0.3
    weight_initial: float = 0.7
    center_bounds_nm: tuple[float, float] | None = None
    lorentz_bounds_nm: tuple[float, float] = (0.0, 10.0)
    Tg_uncertainty_K: float | None = None


class Recipe(BaseModel):
    id: str | None = None
    name: str
    # Legacy: kept for back-compat. New code should set recipe_kind instead.
    diagnostic: str
    # New (Phase 4): discriminator for the new analysis kinds. When None,
    # batch infers from ``diagnostic``.
    recipe_kind: RecipeKind | None = None
    # Common: preprocessing pipeline applied before analysis.
    preprocessing: list[dict[str, Any]] = Field(default_factory=list)
    # Legacy free-form parameter blocks (used by hbeta_voigt / oh_ax / n2_cb / peak_area).
    window_nm: tuple[float, float] | None = None
    fit_model: str | None = None
    fit_parameters: dict[str, Any] = Field(default_factory=dict)
    peak_name: str | None = None
    # Phase 4 typed parameter blocks (set the one matching recipe_kind).
    peak_list: PeakListParams | None = None
    molecular: MolecularParams | None = None
    electron_density: ElectronDensityParams | None = None
    exports: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"
