"""Boltzmann factors for molecular-band demo fitting."""

from __future__ import annotations

import numpy as np

SECOND_RADIATION_CONSTANT_CM_K = 1.438776877


def rotational_boltzmann_factor(energy_upper_cm1: np.ndarray, temperature_K: float) -> np.ndarray:
    """Return Boltzmann factors for upper-state energies in cm^-1."""

    temperature_K = float(temperature_K)
    if temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    energy_upper_cm1 = np.asarray(energy_upper_cm1, dtype=float)
    return np.exp(-SECOND_RADIATION_CONSTANT_CM_K * energy_upper_cm1 / temperature_K)

