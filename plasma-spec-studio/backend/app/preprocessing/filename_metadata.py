"""Extract experiment metadata from spectrum filenames.

Spectrometer software typically writes filenames that encode the run
conditions: ``100kHz_1ms_10_1.xlsx``, ``500kHz_1ms_10_3.xlsx``, etc. This
module parses such patterns into structured metadata that's merged into the
spectrum record at upload time and surfaces in batch result tables.

Two parsing strategies are supported:

1. **Tag regexes**: a default set that matches the user's actual naming
   convention. Each tag has a regex with a named group plus a converter.
2. **User-supplied regex**: a single regex with named groups, used when the
   default tags don't fit. Setting ``user_regex`` overrides the defaults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class TagSpec:
    """One filename-tag matcher."""

    name: str
    pattern: re.Pattern[str]
    converter: Callable[[str], Any]


def _int(value: str) -> int:
    return int(value)


def _float(value: str) -> float:
    return float(value)


# Defaults match the user's actual files (e.g. "100kHz_1ms_10_1.xlsx",
# "750kHz_1ms_10_3.xlsx", "1khz-argon.xlsx"). Case-insensitive for the units
# so both "kHz" and "khz" are accepted.
DEFAULT_TAG_SPECS: tuple[TagSpec, ...] = (
    TagSpec(
        name="pulse_frequency_khz",
        pattern=re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*k?Hz", re.IGNORECASE),
        converter=_float,
    ),
    TagSpec(
        name="burst_period_ms",
        pattern=re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*ms(?![A-Za-z])", re.IGNORECASE),
        converter=_float,
    ),
    TagSpec(
        name="n_cycles",
        pattern=re.compile(r"(?<![A-Za-z0-9])(\d+)\s*(?:cycles?|cyc)(?![A-Za-z])", re.IGNORECASE),
        converter=_int,
    ),
    TagSpec(
        name="voltage_kv",
        pattern=re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*kV(?![A-Za-z])", re.IGNORECASE),
        converter=_float,
    ),
    TagSpec(
        name="gate_delay_ns",
        pattern=re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*ns(?![A-Za-z])", re.IGNORECASE),
        converter=_float,
    ),
    TagSpec(
        name="replicate",
        pattern=re.compile(r"[_-]rep[_-]?(\d+)", re.IGNORECASE),
        converter=_int,
    ),
)


# Template fallback for naming conventions like "100kHz_1ms_10_1": when none
# of the explicit tags match the trailing _10_1 pattern, infer from positional
# numeric tokens.
_POSITIONAL_PATTERN = re.compile(
    r"""
    ^(?P<freq>\d+(?:\.\d+)?)\s*k?Hz       # 100kHz
    [_-](?P<period>\d+(?:\.\d+)?)\s*ms    # _1ms
    [_-](?P<cycles>\d+)                   # _10
    [_-](?P<rep>\d+)                      # _1
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_from_filename(
    filename: str,
    user_regex: str | re.Pattern[str] | None = None,
) -> dict[str, Any]:
    """Return a metadata dict parsed from ``filename``.

    Strips the file extension and any directory prefix. When ``user_regex`` is
    supplied, only its named groups are used. Otherwise the default tag
    matchers are applied; if none of them match, the positional template
    ``<freq>kHz_<ms>ms_<cycles>_<rep>`` is tried.
    """

    stem = _strip_extension_and_dirs(filename)

    if user_regex is not None:
        pattern = user_regex if isinstance(user_regex, re.Pattern) else re.compile(user_regex)
        match = pattern.search(stem)
        if not match:
            return {}
        return {
            key: _try_cast(value)
            for key, value in match.groupdict().items()
            if value is not None
        }

    metadata: dict[str, Any] = {}
    for spec in DEFAULT_TAG_SPECS:
        match = spec.pattern.search(stem)
        if match is None:
            continue
        try:
            metadata[spec.name] = spec.converter(match.group(1))
        except (TypeError, ValueError):
            continue

    # Always also try the positional template - it can fill in fields the
    # individual tag regexes missed (e.g. n_cycles in "100kHz_1ms_10_1" where
    # the bare "10" has no `cycles` suffix).
    pos = _POSITIONAL_PATTERN.match(stem)
    if pos is not None:
        positional = {
            "pulse_frequency_khz": _float(pos.group("freq")),
            "burst_period_ms": _float(pos.group("period")),
            "n_cycles": _int(pos.group("cycles")),
            "replicate": _int(pos.group("rep")),
        }
        for key, value in positional.items():
            metadata.setdefault(key, value)

    metadata["filename_stem"] = stem
    return metadata


def _strip_extension_and_dirs(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base


def _try_cast(value: str) -> Any:
    text = value.strip()
    if not text:
        return None
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text
