"""Spectrum container and helper functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np

from app.core.json_safe import json_safe


@dataclass(slots=True)
class Spectrum:
    """In-memory representation of an optical emission spectrum.

    Wavelength is always stored in nanometers and intensity in arbitrary units
    unless calibrated data are supplied by future modules.
    """

    filename: str
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    preprocessing_history: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.wavelength_nm = np.asarray(self.wavelength_nm, dtype=float)
        self.intensity = np.asarray(self.intensity, dtype=float)
        if self.wavelength_nm.shape != self.intensity.shape:
            raise ValueError("wavelength_nm and intensity arrays must have the same shape")
        if self.wavelength_nm.ndim != 1:
            raise ValueError("spectrum arrays must be one-dimensional")
        if len(self.wavelength_nm) < 2:
            raise ValueError("spectrum must contain at least two data points")
        finite = np.isfinite(self.wavelength_nm) & np.isfinite(self.intensity)
        if not np.all(finite):
            self.wavelength_nm = self.wavelength_nm[finite]
            self.intensity = self.intensity[finite]
        order = np.argsort(self.wavelength_nm)
        self.wavelength_nm = self.wavelength_nm[order]
        self.intensity = self.intensity[order]

    def with_data(
        self,
        wavelength_nm: np.ndarray,
        intensity: np.ndarray,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> "Spectrum":
        """Return a processed copy with an appended preprocessing history item."""

        history = [*self.preprocessing_history, make_history_item(operation, params or {})]
        return Spectrum(
            id=self.id,
            filename=self.filename,
            wavelength_nm=wavelength_nm,
            intensity=intensity,
            metadata=dict(self.metadata),
            preprocessing_history=history,
        )

    def to_dict(self, include_arrays: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "filename": self.filename,
            "metadata": json_safe(self.metadata),
            "preprocessing_history": json_safe(self.preprocessing_history),
        }
        if include_arrays:
            data["wavelength_nm"] = self.wavelength_nm.tolist()
            data["intensity"] = self.intensity.tolist()
        else:
            data["points"] = int(len(self.wavelength_nm))
            data["wavelength_min_nm"] = float(np.min(self.wavelength_nm))
            data["wavelength_max_nm"] = float(np.max(self.wavelength_nm))
        return data


def make_history_item(operation: str, params: dict[str, Any]) -> dict[str, Any]:
    """Create a standardized preprocessing history entry."""

    return {
        "operation": operation,
        "params": params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def spectrum_from_mapping(data: dict[str, Any]) -> Spectrum:
    """Build a Spectrum from an API/storage mapping."""

    return Spectrum(
        id=data.get("id") or str(uuid4()),
        filename=data.get("filename", "spectrum"),
        wavelength_nm=np.asarray(data["wavelength_nm"], dtype=float),
        intensity=np.asarray(data["intensity"], dtype=float),
        metadata=data.get("metadata") or {},
        preprocessing_history=data.get("preprocessing_history") or [],
    )

