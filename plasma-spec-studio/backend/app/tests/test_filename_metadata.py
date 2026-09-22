"""Tests for the filename metadata extractor."""

from __future__ import annotations

import pytest

from app.preprocessing.filename_metadata import extract_from_filename


@pytest.mark.parametrize(
    "filename, expected",
    [
        (
            "100kHz_1ms_10_1.xlsx",
            {
                "pulse_frequency_khz": 100.0,
                "burst_period_ms": 1.0,
                "n_cycles": 10,
                "replicate": 1,
                "filename_stem": "100kHz_1ms_10_1",
            },
        ),
        (
            "750kHz_1ms_10_3.xlsx",
            {
                "pulse_frequency_khz": 750.0,
                "burst_period_ms": 1.0,
                "n_cycles": 10,
                "replicate": 3,
            },
        ),
        (
            "/some/path/250kHz_1ms_10_2.xlsx",
            {
                "pulse_frequency_khz": 250.0,
                "burst_period_ms": 1.0,
                "n_cycles": 10,
                "replicate": 2,
            },
        ),
        (
            "1khz-argon.xlsx",  # mixed-case kHz; no positional template
            {"pulse_frequency_khz": 1.0},
        ),
    ],
)
def test_default_pattern_matches_lab_filenames(filename, expected):
    metadata = extract_from_filename(filename)
    for key, value in expected.items():
        assert metadata.get(key) == value, (
            f"missing/wrong {key}={metadata.get(key)} for {filename}"
        )


def test_user_regex_takes_precedence():
    metadata = extract_from_filename(
        "exp42-Ar-12kV.csv",
        user_regex=r"exp(?P<run_id>\d+)-(?P<gas>[A-Z][a-z]?)-(?P<voltage_kv>\d+)kV",
    )
    assert metadata == {"run_id": 42, "gas": "Ar", "voltage_kv": 12}


def test_no_match_returns_minimal_dict():
    metadata = extract_from_filename("random_name.csv")
    assert metadata == {"filename_stem": "random_name"}
    metadata = extract_from_filename("random_name.csv", user_regex=r"^X(?P<x>\d+)$")
    assert metadata == {}
