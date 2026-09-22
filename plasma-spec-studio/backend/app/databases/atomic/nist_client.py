"""Official NIST ASD line-query client.

The bundled catalog is intentionally small and curated. This module adds the
on-demand path for broader coverage by querying the public NIST ASD Lines CGI
endpoint and normalising its tab-delimited output into the app's atomic catalog
schema.
"""

from __future__ import annotations

import io
import math
import re
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


NIST_LINES_ENDPOINT = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"
USER_AGENT = "PlasmaSpecStudio/0.1 (+local researcher NIST ASD refresh)"

DEFAULT_LOW_TEMPERATURE_PLASMA_SPECIES = [
    "H I",
    "H II",
    "He I",
    "He II",
    "Ar I",
    "Ar II",
    "O I",
    "O II",
    "N I",
    "N II",
    "C I",
    "C II",
    "Ne I",
    "Ne II",
    "Kr I",
    "Xe I",
    "Hg I",
]


@dataclass(frozen=True)
class NistFetchResult:
    species: str
    url: str
    ssl_verified: bool
    line_count: int
    lines: pd.DataFrame


def fetch_nist_lines(
    *,
    species: str,
    wavelength_min_nm: float | None,
    wavelength_max_nm: float | None,
    require_transition_probabilities: bool = False,
    max_lines: int = 20_000,
    timeout_s: float = 30.0,
) -> NistFetchResult:
    """Fetch one species/range from NIST ASD and return normalised rows."""

    species = _normalise_species_label(species)
    if not species:
        raise ValueError("species is required")
    if max_lines < 1:
        raise ValueError("max_lines must be positive")

    url = build_nist_query_url(
        species=species,
        wavelength_min_nm=wavelength_min_nm,
        wavelength_max_nm=wavelength_max_nm,
        require_transition_probabilities=require_transition_probabilities,
        page_size=max_lines,
    )
    request = Request(url, headers={"User-Agent": USER_AGENT})
    text, ssl_verified = _read_url(request, timeout_s=timeout_s)

    lines = parse_nist_lines_tsv(text, species=species)
    if len(lines) > max_lines:
        lines = lines.head(max_lines).copy()
    return NistFetchResult(
        species=species,
        url=url,
        ssl_verified=ssl_verified,
        line_count=int(len(lines)),
        lines=lines,
    )


def _read_url(request: Request, *, timeout_s: float) -> tuple[str, bool]:
    """Read a URL, retrying NIST with an unverified context on local CA failure."""

    try:
        with urlopen(request, timeout=timeout_s) as response:
            return response.read().decode("utf-8-sig", errors="replace"), True
    except URLError as exc:
        reason = str(exc.reason if hasattr(exc, "reason") else exc)
        if "CERTIFICATE_VERIFY_FAILED" not in reason:
            raise
        context = ssl._create_unverified_context()
        with urlopen(request, timeout=timeout_s, context=context) as response:
            return response.read().decode("utf-8-sig", errors="replace"), False


def build_nist_query_url(
    *,
    species: str,
    wavelength_min_nm: float | None,
    wavelength_max_nm: float | None,
    require_transition_probabilities: bool,
    page_size: int,
) -> str:
    """Build the same tab-delimited query submitted by the official form."""

    params: dict[str, Any] = {
        "spectra": species,
        "output_type": "0",  # wavelength
        "low_w": _format_limit(wavelength_min_nm),
        "upp_w": _format_limit(wavelength_max_nm),
        "unit": "1",  # nm
        "submit": "Retrieve Data",
        "de": "0",
        "plot_out": "0",
        "I_scale_type": "1",
        "format": "3",  # tab-delimited text
        "line_out": "1" if require_transition_probabilities else "0",
        "remove_js": "on",
        "en_unit": "0",  # cm^-1
        "output": "0",  # entire result, not paginated
        "page_size": str(page_size),
        "bibrefs": "1",
        "show_obs_wl": "1",
        "show_calc_wl": "1",
        "show_wn": "1",
        "unc_out": "1",
        "order_out": "0",
        # NIST convention: vacuum below 200 nm, air 200-2000 nm, vacuum above.
        "show_av": "2",
        "A_out": "0",
        "intens_out": "on",
        "allowed_out": "1",
        "forbid_out": "1",
        "conf_out": "on",
        "term_out": "on",
        "enrg_out": "on",
        "J_out": "on",
        "g_out": "on",
    }
    return f"{NIST_LINES_ENDPOINT}?{urlencode(params)}"


def parse_nist_lines_tsv(text: str, *, species: str) -> pd.DataFrame:
    """Normalise NIST ASD tab-delimited output into catalog columns."""

    if "<h1>Software error" in text or "Can't use an undefined value" in text:
        raise ValueError("NIST ASD returned a software-error page for this query")
    if "<html" in text.lower() and "\t" not in text:
        raise ValueError("NIST ASD returned HTML instead of tab-delimited data")

    frame = pd.read_csv(io.StringIO(text), sep="\t", dtype=str, keep_default_na=False)
    frame = frame.drop(columns=[c for c in frame.columns if not str(c).strip()], errors="ignore")
    if frame.empty or len(frame.columns) == 0:
        return _empty_catalog_frame()

    frame = frame.map(_clean_cell)
    wavelength_info = _pick_wavelength(frame)
    wavelength = wavelength_info["wavelength"]
    keep = wavelength.notna()
    if not keep.any():
        return _empty_catalog_frame()
    frame = frame.loc[keep].copy()
    wavelength = wavelength.loc[keep]

    output = pd.DataFrame(
        {
            "species": _normalise_species_label(species),
            "wavelength_air_nm": wavelength.astype(float),
            "A_ki_s_1": _numeric_series(frame.get("Aki(s^-1)")),
            "acc_A": _string_series(frame.get("Acc")),
            "E_i_cm1": _numeric_series(frame.get("Ei(cm-1)")),
            "E_k_cm1": _numeric_series(frame.get("Ek(cm-1)")),
            "g_i": _numeric_series(frame.get("g_i")),
            "g_k": _numeric_series(frame.get("g_k")),
            "lower_term": _level_label(frame, "i"),
            "upper_term": _level_label(frame, "k"),
            "transition": _transition_label(frame),
            "source": "NIST ASD live refresh",
            "notes": _notes(frame, wavelength_info["source_column"]),
            "nist_wavelength_source": wavelength_info["source_column"],
            "wavenumber_cm1": _numeric_series(frame.get("wn(cm-1)")),
            "relative_intensity": _numeric_series(frame.get("intens")),
            "transition_type": _string_series(frame.get("Type")),
            "tp_ref": _string_series(frame.get("tp_ref")),
            "line_ref": _string_series(frame.get("line_ref")),
        }
    )

    output = output.where(pd.notna(output), None)
    return output.sort_values("wavelength_air_nm").reset_index(drop=True)


def _empty_catalog_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "species",
            "wavelength_air_nm",
            "A_ki_s_1",
            "acc_A",
            "E_i_cm1",
            "E_k_cm1",
            "g_i",
            "g_k",
            "lower_term",
            "upper_term",
            "transition",
            "source",
            "notes",
        ]
    )


def _pick_wavelength(frame: pd.DataFrame) -> dict[str, Any]:
    candidates = [
        "obs_wl_air(nm)",
        "ritz_wl_air(nm)",
        "obs_wl_vac(nm)",
        "ritz_wl_vac(nm)",
    ]
    for column in list(frame.columns):
        if column not in candidates and column.startswith(("obs_wl_", "ritz_wl_")) and "(nm)" in column:
            candidates.append(column)

    chosen = pd.Series([math.nan] * len(frame), index=frame.index, dtype=float)
    source = pd.Series([""] * len(frame), index=frame.index, dtype=object)
    for column in candidates:
        if column not in frame.columns:
            continue
        values = _numeric_series(frame[column])
        mask = chosen.isna() & values.notna()
        chosen.loc[mask] = values.loc[mask]
        source.loc[mask] = column
    return {"wavelength": chosen, "source_column": source}


def _numeric_series(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def _string_series(series: pd.Series | None, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        if index is None:
            return pd.Series(dtype=object)
        return pd.Series([None] * len(index), index=index, dtype=object)
    return series.astype(object).map(_clean_cell).replace({"": None}).astype(object)


def _level_label(frame: pd.DataFrame, suffix: str) -> pd.Series:
    conf = _string_series(frame.get(f"conf_{suffix}"), frame.index).fillna("")
    term = _string_series(frame.get(f"term_{suffix}"), frame.index).fillna("")
    j_value = _string_series(frame.get(f"J_{suffix}"), frame.index).fillna("")

    labels: list[str | None] = []
    for conf_i, term_i, j_i in zip(conf, term, j_value, strict=False):
        parts = [part for part in (conf_i, term_i) if _has_text(part)]
        if _has_text(j_i):
            parts.append(f"J={j_i}")
        labels.append(" ".join(parts) or None)
    return pd.Series(labels, index=frame.index, dtype=object)


def _transition_label(frame: pd.DataFrame) -> pd.Series:
    lower = _level_label(frame, "i")
    upper = _level_label(frame, "k")
    transition_type = _string_series(frame.get("Type"), frame.index).fillna("")
    labels: list[str | None] = []
    for lo, hi, kind in zip(lower, upper, transition_type, strict=False):
        if _has_text(lo) and _has_text(hi):
            label = f"{lo} -> {hi}"
        elif _has_text(kind):
            label = kind
        else:
            label = None
        if label and _has_text(kind) and kind not in label:
            label = f"{label} ({kind})"
        labels.append(label)
    return pd.Series(labels, index=frame.index, dtype=object)


def _notes(frame: pd.DataFrame, wavelength_source: pd.Series) -> pd.Series:
    tp_ref = _string_series(frame.get("tp_ref"), frame.index).fillna("")
    line_ref = _string_series(frame.get("line_ref"), frame.index).fillna("")
    transition_type = _string_series(frame.get("Type"), frame.index).fillna("")
    notes: list[str | None] = []
    for tp, line, kind, wl_source in zip(tp_ref, line_ref, transition_type, wavelength_source, strict=False):
        parts = [f"wavelength={wl_source}" if wl_source else ""]
        if kind:
            parts.append(f"type={kind}")
        if tp:
            parts.append(f"tp_ref={tp}")
        if line:
            parts.append(f"line_ref={line}")
        notes.append("; ".join(part for part in parts if part) or None)
    return pd.Series(notes, index=frame.index, dtype=object)


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    if text in {'""', "''"}:
        return ""
    text = text.strip('"').strip()
    text = re.sub(r"\s+", " ", text)
    return "" if text.lower() in {"", "--", "—", "nan", "none", "na", "<na>"} else text


def _has_text(value: object) -> bool:
    return bool(_clean_cell(value))


def _normalise_species_label(species: str) -> str:
    return re.sub(r"\s+", " ", species.strip())


def _format_limit(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):g}"
