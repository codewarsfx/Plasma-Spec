"""Pydantic schemas for spectra and preprocessing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PreprocessingOperation(BaseModel):
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


class SpectrumMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    gas: str | None = None
    liquid: str | None = None
    pfas_concentration_ppm: float | None = None
    methanol_concentration: str | None = None
    pulse_mode: str | None = None
    uniform_frequency_khz: float | None = None
    internal_frequency_khz: float | None = None
    burst_period_ms: float | None = None
    n_cycles: int | None = None
    voltage_kv: float | None = None
    gate_delay_ns: float | None = None
    gate_width_ns: float | None = None
    replicate: int | None = None
    date: str | None = None


class SpectrumSummary(BaseModel):
    id: str
    filename: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    preprocessing_history: list[dict[str, Any]] = Field(default_factory=list)
    points: int | None = None
    wavelength_min_nm: float | None = None
    wavelength_max_nm: float | None = None
    created_at: str | None = None


class SpectrumResponse(BaseModel):
    id: str
    filename: str
    wavelength_nm: list[float]
    intensity: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)
    preprocessing_history: list[dict[str, Any]] = Field(default_factory=list)


class PreprocessRequest(BaseModel):
    spectrum_id: str
    operations: list[PreprocessingOperation]
    save_as_new: bool = False
    background_spectrum_id: str | None = None


class PreprocessResponse(BaseModel):
    spectrum: SpectrumResponse
    mode: Literal["preview", "saved"]
