"""Pydantic schemas for fitting, line ID, and batch routes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.spectrum_schema import PreprocessingOperation


def _ordered_pair(value: tuple[float, float] | None, name: str) -> tuple[float, float] | None:
    """Validate a finite ordered numeric pair."""

    if value is None:
        return None
    lo, hi = float(value[0]), float(value[1])
    if lo >= hi:
        raise ValueError(f"{name} must be ordered low < high")
    return (lo, hi)


def _positive_values(values: list[float] | None, name: str) -> list[float] | None:
    if values is None:
        return None
    if any(float(value) <= 0 for value in values):
        raise ValueError(f"{name} values must be positive")
    return [float(value) for value in values]


class HbetaFitRequest(BaseModel):
    spectrum_id: str
    window_nm: tuple[float, float] = (484.0, 488.0)
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    model: Literal["gaussian", "lorentzian", "voigt"] = "voigt"
    center_bounds: tuple[float, float] = (485.8, 486.4)
    sigma_bounds: tuple[float, float] = (0.001, 1.0)
    gamma_bounds: tuple[float, float] = (0.001, 1.0)

    @field_validator("window_nm", "center_bounds", "sigma_bounds", "gamma_bounds")
    @classmethod
    def validate_ordered_pairs(cls, value: tuple[float, float], info):
        return _ordered_pair(value, info.field_name)


class MolecularFitRequest(BaseModel):
    spectrum_id: str
    window_nm: tuple[float, float]
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    initial_trot_K: float = Field(default=1200.0, gt=0)
    initial_tvib_K: float | None = Field(default=None, gt=0)
    trot_bounds_K: tuple[float, float] = (250.0, 6000.0)
    tvib_bounds_K: tuple[float, float] = (250.0, 10_000.0)
    instrument_fwhm_nm: float = Field(default=0.12, gt=0)
    wavelength_shift_nm: float = 0.0
    database_source: Literal["auto", "sqlite", "demo"] = "auto"
    wavelength_shift_bounds_nm: tuple[float, float] = (-2.0, 2.0)
    instrument_fwhm_bounds_nm: tuple[float, float] = (0.01, 2.0)
    fit_tvib: bool = False
    instrument_profile: Literal["gaussian", "voigt"] = "gaussian"
    instrument_lorentz_fwhm_nm: float = Field(default=0.0, ge=0)
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] = (0.0, 1.0)
    fit_instrument_lorentz: bool = False
    multi_restart_trot_K: list[float] | None = None

    @field_validator(
        "window_nm",
        "trot_bounds_K",
        "tvib_bounds_K",
        "wavelength_shift_bounds_nm",
        "instrument_fwhm_bounds_nm",
        "instrument_lorentz_fwhm_bounds_nm",
    )
    @classmethod
    def validate_ordered_pairs(cls, value: tuple[float, float], info):
        return _ordered_pair(value, info.field_name)

    @field_validator("multi_restart_trot_K")
    @classmethod
    def validate_restart_temperatures(cls, value: list[float] | None):
        return _positive_values(value, "multi_restart_trot_K")


class UnifiedMolecularFitRequest(MolecularFitRequest):
    """Request for the unified /api/fit/molecular endpoint."""

    species_id: Literal["OH_AX", "N2_CB", "N2plus_BX", "NH_AX", "NO_BX"]


class StateByStateMolecularFitRequest(BaseModel):
    """Temperature-independent molecular state-population fit."""

    spectrum_id: str
    species_id: Literal["OH_AX", "N2_CB", "N2plus_BX", "NH_AX", "NO_BX"]
    window_nm: tuple[float, float]
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    instrument_fwhm_nm: float = Field(default=0.12, gt=0)
    wavelength_shift_nm: float = 0.0
    database_source: Literal["auto", "sqlite", "demo"] = "auto"
    max_states: int = Field(default=40, ge=1, le=250)
    min_state_relative_strength: float = Field(default=0.0, ge=0, lt=1)
    wavelength_shift_bounds_nm: tuple[float, float] = (-2.0, 2.0)
    instrument_fwhm_bounds_nm: tuple[float, float] = (0.01, 2.0)
    fit_wavelength_shift: bool = True
    fit_instrument_fwhm: bool = True
    instrument_profile: Literal["gaussian", "voigt"] = "gaussian"
    instrument_lorentz_fwhm_nm: float = Field(default=0.0, ge=0)

    @field_validator(
        "window_nm",
        "wavelength_shift_bounds_nm",
        "instrument_fwhm_bounds_nm",
    )
    @classmethod
    def validate_ordered_pairs(cls, value: tuple[float, float], info):
        return _ordered_pair(value, info.field_name)


class AtomicForwardFitRequest(BaseModel):
    """Relative NIST-backed atomic forward-model fit."""

    spectrum_id: str
    species: list[str] = Field(default_factory=lambda: ["H I", "Ar I", "O I", "N II"])
    window_nm: tuple[float, float] = (300.0, 900.0)
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    initial_temperature_K: float = Field(default=9000.0, gt=0)
    temperature_bounds_K: tuple[float, float] = (1000.0, 30_000.0)
    fit_temperature: bool = True
    instrument_profile: Literal["gaussian", "voigt"] = "gaussian"
    instrument_fwhm_nm: float = Field(default=0.15, gt=0)
    instrument_fwhm_bounds_nm: tuple[float, float] = (0.02, 2.0)
    fit_instrument_fwhm: bool = True
    instrument_lorentz_fwhm_nm: float = Field(default=0.0, ge=0)
    instrument_lorentz_fwhm_bounds_nm: tuple[float, float] = (0.0, 2.0)
    fit_instrument_lorentz: bool = False
    wavelength_shift_nm: float = 0.0
    wavelength_shift_bounds_nm: tuple[float, float] = (-1.0, 1.0)
    fit_wavelength_shift: bool = True
    species_weights: dict[str, float] = Field(default_factory=dict)
    fit_species_scales: bool = True
    baseline_order: Literal[0, 1] = 1
    max_lines: int = Field(default=3000, ge=1, le=50_000)
    top_contributions: int = Field(default=40, ge=0, le=250)

    @field_validator(
        "window_nm",
        "temperature_bounds_K",
        "instrument_fwhm_bounds_nm",
        "instrument_lorentz_fwhm_bounds_nm",
        "wavelength_shift_bounds_nm",
    )
    @classmethod
    def validate_ordered_pairs(cls, value: tuple[float, float], info):
        return _ordered_pair(value, info.field_name)


class ElectronDensityRequest(BaseModel):
    """Lab Stark workflow request (H-alpha Gigosos calibration by default)."""

    spectrum_id: str
    Tg_K: float = Field(gt=0)
    instrument_gauss_fwhm_nm: float = Field(default=0.13, gt=0)
    line: Literal["halpha", "hbeta"] = "halpha"
    model: Literal["single_voigt", "two_voigt"] = "single_voigt"
    window_nm: tuple[float, float] | None = None
    intensity_threshold_rel: float = Field(default=0.05, ge=0, lt=1)
    center_initial_nm: float | None = None
    lorentz_initial_nm: float = Field(default=1.0, gt=0)
    lorentz2_initial_nm: float = Field(default=0.3, gt=0)
    weight_initial: float = Field(default=0.7, ge=0, le=1)
    center_bounds_nm: tuple[float, float] | None = None
    lorentz_bounds_nm: tuple[float, float] = (0.0, 10.0)
    Tg_uncertainty_K: float | None = Field(default=None, ge=0)
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)

    @field_validator("window_nm", "center_bounds_nm", "lorentz_bounds_nm")
    @classmethod
    def validate_ordered_pairs(cls, value: tuple[float, float] | None, info):
        return _ordered_pair(value, info.field_name)


class PeakAreaRequest(BaseModel):
    spectrum_id: str
    name: str = "custom_peak"
    window_nm: tuple[float, float]
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)

    @field_validator("window_nm")
    @classmethod
    def validate_window(cls, value: tuple[float, float]):
        return _ordered_pair(value, "window_nm")


class PeakListEntry(BaseModel):
    """One peak in a wavelength-list analysis request."""

    label: str | None = None
    center_nm: float
    half_width_nm: float | None = Field(default=None, gt=0)
    fit_model: Literal["gaussian", "lorentzian", "voigt"] | None = None
    species: str | None = None
    transition: str | None = None
    notes: str | None = None


class PeakListRequest(BaseModel):
    spectrum_id: str
    peaks: list[PeakListEntry]
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    default_half_width_nm: float = Field(default=0.5, gt=0)
    default_fit_model: Literal["gaussian", "lorentzian", "voigt"] | None = None


class LineIdentificationRequest(BaseModel):
    spectrum_id: str
    window_nm: tuple[float, float] | None = None
    preprocessing: list[PreprocessingOperation] = Field(default_factory=list)
    threshold_rel: float = Field(default=0.1, ge=0, lt=1)
    tolerance_nm: float = Field(default=0.25, gt=0)

    @field_validator("window_nm")
    @classmethod
    def validate_window(cls, value: tuple[float, float] | None):
        return _ordered_pair(value, "window_nm")


class ExportResultRequest(BaseModel):
    result: dict[str, Any]
    formats: list[Literal["json", "csv", "png"]] = Field(default_factory=lambda: ["json", "csv"])


class ReportRequest(BaseModel):
    """Render a per-result report.

    Pass the full result dict from any of the fit endpoints. The
    ``formats`` field selects which output(s) to produce. HTML is
    self-contained (PNG embedded); PDF is one page rendered via matplotlib.
    """

    result: dict[str, Any]
    formats: list[Literal["html", "pdf"]] = Field(default_factory=lambda: ["html"])


class FitResultResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    spectrum_id: str | None = None
    filename: str | None = None
    diagnostic: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    fit_quality: str
    warnings: list[str] = Field(default_factory=list)


class BatchRunRequest(BaseModel):
    spectrum_ids: list[str]
    recipe: dict[str, Any] | None = None
    recipe_id: str | None = None
