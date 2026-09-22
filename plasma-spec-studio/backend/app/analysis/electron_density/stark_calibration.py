"""Stark broadening to electron density calibration.

This module is a faithful port of the lab MATLAB scripts the user provided
(`Ne.m`, `Lorentz.m`, `Gaussian.m`, `Voigt.m`, `TwoVoigt.m`, `ElectronDensity.m`,
`ElectronDensity_TwoVoigt.m`). Each formula is annotated with its MATLAB origin
and the physical interpretation.

The primary line is H-alpha (656.279 nm) with the lab's Gigosos-Cardenoso /
Konjevic constant C = 1.78 nm. An H-beta variant with C = 4.84 nm (Gigosos-
Gonzalez-Konjevic 2003) is included as an optional cross-check; H-beta is
*not* validated against the user's specific lab setup, so the result is
returned with an explicit `validated=False` flag.

The math, in one place:

    Lorentzian width found from fit:    wL  [nm]
    van der Waals broadening:           wvdW = 5.12 / Tg^0.7    [nm]   (H-alpha, Ar perturbers)
    Stark width:                        wS   = wL - wvdW         [nm]   (linear subtraction)
    Electron density:                   ne   = (wS / C)^1.5 * 1e17   [cm^-3]

C depends on the line; the constants are documented in ``STARK_CALIBRATIONS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LineId = Literal["halpha", "hbeta"]


@dataclass(frozen=True, slots=True)
class StarkCalibration:
    """One calibration entry for the (Stark FWHM -> n_e) conversion."""

    line: LineId
    wavelength_nm: float
    stark_constant_nm: float
    vdw_prefactor_nm: float
    vdw_tg_exponent: float
    validated: bool
    source: str
    notes: str


# C = 1.78 nm matches the lab MATLAB constant in Ne.m (line 6/7) for H-alpha.
# vdW formula 5.12 / Tg^0.7 matches Ne.m line 3 for H-alpha with Ar perturbers.
HALPHA_LAB = StarkCalibration(
    line="halpha",
    wavelength_nm=656.279,
    stark_constant_nm=1.78,
    vdw_prefactor_nm=5.12,
    vdw_tg_exponent=0.7,
    validated=True,
    source="Lab MATLAB scripts (Ne.m). Consistent with Gigosos-Cardenoso H-alpha calibration.",
    notes=(
        "Stark width Δλ_S [nm] -> n_e = (Δλ_S / 1.78)^1.5 * 1e17 cm^-3. "
        "van der Waals broadening Δλ_vdW = 5.12 / Tg^0.7 nm assumes H-alpha "
        "with Ar perturbers and is subtracted linearly from the fitted Lorentzian width."
    ),
)

# H-beta cross-check. Gigosos-Gonzalez-Konjevic 2003 gives ne = (Δλ_S / C)^1.5 * 1e17
# with C ≈ 4.84 nm and weak temperature dependence. Phase 1.7 already noted this
# is not validated against the user's lab.
HBETA_CROSSCHECK = StarkCalibration(
    line="hbeta",
    wavelength_nm=486.135,
    stark_constant_nm=4.84,
    vdw_prefactor_nm=0.0,
    vdw_tg_exponent=0.0,
    validated=False,
    source="Gigosos-Gonzalez-Konjevic 2003 (literature cross-check, not lab-calibrated).",
    notes=(
        "H-beta Stark calibration with C=4.84 nm. The van der Waals correction "
        "for H-beta is much smaller than for H-alpha; here it is set to zero. "
        "Use this only as a sanity-check against the lab H-alpha result."
    ),
)


STARK_CALIBRATIONS: dict[LineId, StarkCalibration] = {
    "halpha": HALPHA_LAB,
    "hbeta": HBETA_CROSSCHECK,
}


def van_der_waals_fwhm_nm(Tg_K: float, calibration: StarkCalibration = HALPHA_LAB) -> float:
    """Van der Waals broadening contribution in nm.

    From ``Ne.m`` line 3 for H-alpha: ``w_vdw = 5.12 / Tg^0.7``. The fact that
    vdW broadening is a Lorentzian profile is what justifies the linear
    subtraction from the fitted Lorentzian width to recover the Stark width.
    """

    if Tg_K <= 0:
        raise ValueError("gas temperature must be positive")
    if calibration.vdw_prefactor_nm == 0:
        return 0.0
    return calibration.vdw_prefactor_nm / (float(Tg_K) ** calibration.vdw_tg_exponent)


def stark_fwhm_nm(
    lorentzian_fwhm_nm: float,
    Tg_K: float,
    calibration: StarkCalibration = HALPHA_LAB,
) -> tuple[float, float]:
    """Return ``(stark_fwhm_nm, vdw_fwhm_nm)``.

    Lorentzian widths from the Voigt fit are the sum of Stark + van der Waals
    broadening: ``wL = wS + wvdW`` (linear because both are Lorentzian).
    """

    vdw = van_der_waals_fwhm_nm(Tg_K, calibration)
    stark = float(lorentzian_fwhm_nm) - vdw
    return stark, vdw


def electron_density_cm3(
    lorentzian_fwhm_nm: float,
    Tg_K: float,
    calibration: StarkCalibration = HALPHA_LAB,
) -> dict[str, float | bool | str | None]:
    """Compute electron density from a fitted Lorentzian width.

    Mirrors ``Ne.m`` exactly for the H-alpha calibration. Returns a dict with
    every intermediate value so the UI / API can show the full traceability
    chain (Lorentzian FWHM -> vdW -> Stark -> n_e).

    If ``stark_fwhm_nm <= 0`` (the vdW correction larger than the fitted
    Lorentzian width), n_e is reported as ``None`` and the result includes a
    warning - this indicates the line is too narrow to be Stark-dominated and
    the diagnostic is unreliable at this n_e level.
    """

    stark, vdw = stark_fwhm_nm(lorentzian_fwhm_nm, Tg_K, calibration)
    warning: str | None = None
    if stark <= 0:
        ne_value: float | None = None
        warning = (
            f"Stark FWHM is {stark:.4f} nm (Lorentzian FWHM {lorentzian_fwhm_nm:.4f} nm "
            f"<= vdW FWHM {vdw:.4f} nm at Tg={Tg_K:.0f} K). Electron density cannot be "
            "computed - the line is dominated by van der Waals broadening or noise."
        )
    else:
        ne_value = (stark / calibration.stark_constant_nm) ** 1.5 * 1.0e17
    return {
        "line": calibration.line,
        "wavelength_nm": calibration.wavelength_nm,
        "lorentzian_fwhm_nm": float(lorentzian_fwhm_nm),
        "vdw_fwhm_nm": float(vdw),
        "stark_fwhm_nm": float(stark),
        "stark_constant_nm": calibration.stark_constant_nm,
        "Tg_K": float(Tg_K),
        "electron_density_cm3": ne_value,
        "validated": calibration.validated,
        "source": calibration.source,
        "warning": warning,
    }


def two_population_electron_density(
    lorentz_fwhm_nm_pop1: float,
    lorentz_fwhm_nm_pop2: float,
    weight_pop1: float,
    Tg_K: float,
    calibration: StarkCalibration = HALPHA_LAB,
) -> dict[str, object]:
    """Two-population n_e following ``ElectronDensity_TwoVoigt.m`` + ``Ne.m`` line 8.

    ``ne = a * ne(wL1) + (1 - a) * ne(wL2)``. Each population's n_e uses the
    same vdW correction (single Tg) and the same Stark constant.
    """

    a = float(weight_pop1)
    if not (0.0 <= a <= 1.0):
        raise ValueError("two-population weight 'a' must lie in [0, 1]")
    pop1 = electron_density_cm3(lorentz_fwhm_nm_pop1, Tg_K, calibration)
    pop2 = electron_density_cm3(lorentz_fwhm_nm_pop2, Tg_K, calibration)

    ne1 = pop1["electron_density_cm3"]
    ne2 = pop2["electron_density_cm3"]
    if ne1 is None or ne2 is None:
        ne_total: float | None = None
    else:
        ne_total = a * float(ne1) + (1.0 - a) * float(ne2)

    return {
        "line": calibration.line,
        "wavelength_nm": calibration.wavelength_nm,
        "weight_pop1": a,
        "weight_pop2": 1.0 - a,
        "Tg_K": float(Tg_K),
        "population_1": pop1,
        "population_2": pop2,
        "electron_density_cm3": ne_total,
        "validated": calibration.validated,
        "source": calibration.source,
    }
