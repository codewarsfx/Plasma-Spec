"""Project-wide scientific constants and defaults."""

from __future__ import annotations

SOFTWARE_NAME = "PlasmaSpec Studio"
SOFTWARE_VERSION = "0.1.0"

DEMO_DATABASE_WARNING = (
    "Demo database used. Results are for software testing only and should not be "
    "interpreted as validated plasma temperatures."
)

H_BETA_CENTER_NM = 486.13
H_ALPHA_CENTER_NM = 656.28

DIAGNOSTIC_WINDOWS_NM: dict[str, tuple[float, float]] = {
    "OH(A-X)": (306.0, 312.0),
    "N2(C-B) 337": (334.0, 339.0),
    "N2(C-B) 357": (355.0, 359.0),
    "N2(C-B) 380": (379.0, 382.0),
    "N2+ first negative": (390.0, 392.0),
    "Hbeta": (484.0, 488.0),
    "Halpha": (654.0, 658.0),
    "O 777": (775.0, 780.0),
    "O 844": (842.0, 846.0),
}

DEFAULT_METADATA_FIELDS = [
    "gas",
    "liquid",
    "pfas_concentration_ppm",
    "methanol_concentration",
    "pulse_mode",
    "uniform_frequency_khz",
    "internal_frequency_khz",
    "burst_period_ms",
    "n_cycles",
    "voltage_kv",
    "gate_delay_ns",
    "gate_width_ns",
    "replicate",
    "date",
]

