"""Robust spectrum import utilities (text + Excel)."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.spectrum import Spectrum


WAVELENGTH_NAMES = ("wavelength", "lambda", "wl", "wave", "nm")
INTENSITY_NAMES = ("intensity", "counts", "signal", "radiance", "emission", "au", "a.u.")
EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls")


def load_spectrum_file(
    path: str | Path,
    wavelength_column: str | int | None = None,
    intensity_column: str | int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Spectrum:
    """Load a spectrum from CSV, TSV, TXT, ASC, or Excel (XLSX/XLSM) file."""

    path = Path(path)
    if path.suffix.lower() in EXCEL_EXTENSIONS:
        return load_spectrum_excel(
            path,
            wavelength_column=wavelength_column,
            intensity_column=intensity_column,
            metadata=metadata,
        )
    return load_spectrum_text(
        path.read_text(encoding="utf-8-sig"),
        filename=path.name,
        wavelength_column=wavelength_column,
        intensity_column=intensity_column,
        metadata=metadata,
    )


def load_spectrum_excel(
    source: str | Path | bytes,
    filename: str | None = None,
    sheet_name: str | int | None = None,
    wavelength_column: str | int | None = None,
    intensity_column: str | int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Spectrum:
    """Load a spectrum from an Excel workbook.

    Handles Avantes/Ocean Insight-style sheets where the top rows are key/value
    metadata (Int.time, NrOfAverages, Smoothing, ...) and the data starts after
    a "Wavelength [nm]" marker row.
    """

    if isinstance(source, (str, Path)):
        path = Path(source)
        if filename is None:
            filename = path.name
        buffer: Any = path
    else:
        if filename is None:
            filename = "uploaded_spectrum.xlsx"
        buffer = io.BytesIO(source)

    raw = pd.read_excel(buffer, sheet_name=sheet_name, header=None)
    if isinstance(raw, dict):  # multi-sheet -> pick first
        sheet_pick = next(iter(raw.values())) if raw else None
        if sheet_pick is None:
            raise ValueError("Excel workbook contains no sheets")
        raw = sheet_pick

    extracted_metadata: dict[str, Any] = {}
    data_start_row, marker_wavelength_col = _find_excel_data_start(
        raw, extracted_metadata
    )
    if data_start_row is None:
        raise ValueError(
            "could not locate numeric wavelength/intensity rows in the workbook"
        )

    table = raw.iloc[data_start_row:].reset_index(drop=True)
    # Remember which original columns survive when we drop all-NaN columns so
    # we can translate the marker-discovered wavelength column index.
    numeric = table.apply(pd.to_numeric, errors="coerce")
    keep_columns = [
        col for col in numeric.columns if not numeric[col].dropna().empty
    ]
    if len(keep_columns) < 2:
        raise ValueError(
            "Excel sheet has fewer than two numeric columns after the header block"
        )
    column_translation = {original: idx for idx, original in enumerate(keep_columns)}
    numeric = numeric[keep_columns].dropna(axis=0, how="all").reset_index(drop=True)
    if numeric.shape[0] < 2:
        raise ValueError(
            "Excel sheet has fewer than two numeric data rows after the header block"
        )
    numeric.columns = [str(i) for i in range(numeric.shape[1])]
    table = numeric

    if (
        wavelength_column is None
        and marker_wavelength_col is not None
        and marker_wavelength_col in column_translation
    ):
        wavelength_column = column_translation[marker_wavelength_col]

    wavelength_idx, intensity_idx = _select_columns(
        table, wavelength_column, intensity_column
    )
    wavelength = table.iloc[:, wavelength_idx].to_numpy(dtype=float)
    intensity = table.iloc[:, intensity_idx].to_numpy(dtype=float)
    finite = np.isfinite(wavelength) & np.isfinite(intensity)
    if finite.sum() < 2:
        raise ValueError(
            "Excel sheet does not contain enough finite wavelength/intensity rows"
        )

    combined_metadata: dict[str, Any] = {**extracted_metadata, **(metadata or {})}
    return Spectrum(
        filename=filename,
        wavelength_nm=wavelength[finite],
        intensity=intensity[finite],
        metadata=combined_metadata,
    )


def _find_excel_data_start(
    frame: pd.DataFrame,
    extracted_metadata: dict[str, Any],
    scan_rows: int = 40,
) -> tuple[int | None, int | None]:
    """Find the first row of numeric spectrum data and (if marked) the column
    that holds wavelengths.

    Returns ``(data_start_row, wavelength_column_index)``. The column index is
    populated only when the workbook contains an explicit ``Wavelength [nm]``
    marker. Otherwise it is ``None`` and the caller falls back to the column
    auto-detector.
    """

    n_rows = min(int(frame.shape[0]), scan_rows)
    explicit_start: int | None = None
    wavelength_col: int | None = None
    for row_idx in range(n_rows):
        cells = list(frame.iloc[row_idx].tolist())
        first = cells[0] if cells else None
        # Capture obvious key/value metadata pairs like "Int.time[ms]-->: 5000".
        if (
            isinstance(first, str)
            and ("-->" in first or first.endswith(":"))
            and len(cells) >= 2
            and cells[1] is not None
        ):
            key = _normalize_metadata_key(first)
            extracted_metadata.setdefault(key, _coerce_metadata_value(cells[1]))
        for col_idx, cell in enumerate(cells):
            if not isinstance(cell, str):
                continue
            cell_lower = cell.strip().lower()
            if any(token in cell_lower for token in ("wavelength", "lambda")) and any(
                unit in cell_lower for unit in ("nm", "[nm]", "(nm)")
            ):
                explicit_start = row_idx + 1
                wavelength_col = col_idx
                break
        if explicit_start is not None:
            break
        if _looks_like_number(first):
            return row_idx, None
    if explicit_start is not None and explicit_start < frame.shape[0]:
        return explicit_start, wavelength_col
    # Fall through: search the rest of the table for the first numeric row.
    for row_idx in range(frame.shape[0]):
        if _looks_like_number(frame.iat[row_idx, 0]):
            return row_idx, None
    return None, None


def _looks_like_number(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return not (isinstance(value, float) and np.isnan(value))
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def _normalize_metadata_key(raw: str) -> str:
    cleaned = raw.replace("-->", "").replace(":", "").strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^\w\[\]\(\)\.\-]", "_", cleaned)
    return cleaned.lower()


def _coerce_metadata_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text


def load_spectrum_text(
    text: str,
    filename: str = "uploaded_spectrum",
    wavelength_column: str | int | None = None,
    intensity_column: str | int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Spectrum:
    """Parse spectrum text and infer wavelength/intensity columns when possible.

    Header lines are tolerated. The parser first tries a table read with an
    inferred delimiter, then falls back to extracting numeric pairs from ASC-like
    lines. Users can override columns by index or header name.
    """

    if not text.strip():
        raise ValueError("spectrum file is empty")

    table = _read_table(text)
    if table is None or table.shape[1] < 2:
        table = _numeric_pair_table(text)
    if table is None or table.shape[1] < 2:
        raise ValueError("could not find at least two numeric spectrum columns")

    wavelength_idx, intensity_idx = _select_columns(table, wavelength_column, intensity_column)
    wavelength = table.iloc[:, wavelength_idx].to_numpy(dtype=float)
    intensity = table.iloc[:, intensity_idx].to_numpy(dtype=float)
    finite = np.isfinite(wavelength) & np.isfinite(intensity)
    if finite.sum() < 2:
        raise ValueError("spectrum does not contain enough finite wavelength/intensity rows")
    return Spectrum(
        filename=filename,
        wavelength_nm=wavelength[finite],
        intensity=intensity[finite],
        metadata=metadata or {},
    )


def load_metadata_csv(path: str | Path) -> list[dict[str, Any]]:
    """Load experiment metadata rows from CSV."""

    frame = pd.read_csv(path)
    return frame.where(pd.notnull(frame), None).to_dict(orient="records")


def _read_table(text: str) -> pd.DataFrame | None:
    delimiter = _guess_delimiter(text)
    candidates: list[pd.DataFrame] = []
    for header in ("infer", None):
        try:
            frame = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                engine="python",
                comment="#",
                header=header,
                skip_blank_lines=True,
            )
        except Exception:
            continue
        numeric = frame.apply(pd.to_numeric, errors="coerce")
        numeric = numeric.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if numeric.shape[0] >= 2 and numeric.shape[1] >= 2:
            if header is None:
                numeric.columns = [str(i) for i in range(numeric.shape[1])]
            else:
                numeric.columns = [str(c).strip() for c in numeric.columns]
            candidates.append(numeric)
    if not candidates:
        return None
    named = [
        candidate
        for candidate in candidates
        if not all(_looks_numeric(str(column)) for column in candidate.columns)
    ]
    if named:
        return max(named, key=len)
    return max(candidates, key=len)


def _numeric_pair_table(text: str) -> pd.DataFrame | None:
    rows: list[list[float]] = []
    for line in text.splitlines():
        numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
        if len(numbers) >= 2:
            rows.append([float(numbers[0]), float(numbers[1])])
    if len(rows) < 2:
        return None
    return pd.DataFrame(rows, columns=["wavelength_nm", "intensity"])


def _guess_delimiter(text: str) -> str | None:
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t; ")
        if dialect.delimiter == " ":
            return r"\s+"
        return dialect.delimiter
    except Exception:
        return None


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _select_columns(
    frame: pd.DataFrame,
    wavelength_column: str | int | None,
    intensity_column: str | int | None,
) -> tuple[int, int]:
    if wavelength_column is not None and intensity_column is not None:
        return _column_index(frame, wavelength_column), _column_index(frame, intensity_column)

    names = [str(c).lower().strip() for c in frame.columns]
    wavelength_idx = _find_named_index(names, WAVELENGTH_NAMES)
    intensity_idx = _find_named_index(names, INTENSITY_NAMES)

    if wavelength_column is not None:
        wavelength_idx = _column_index(frame, wavelength_column)
    if intensity_column is not None:
        intensity_idx = _column_index(frame, intensity_column)

    if wavelength_idx is None:
        wavelength_idx = _infer_wavelength_column(frame)
    if intensity_idx is None:
        candidates = [i for i in range(frame.shape[1]) if i != wavelength_idx]
        if not candidates:
            raise ValueError("could not infer intensity column")
        intensity_idx = candidates[0]

    if wavelength_idx == intensity_idx:
        raise ValueError("wavelength and intensity columns must be different")
    return int(wavelength_idx), int(intensity_idx)


def _column_index(frame: pd.DataFrame, column: str | int) -> int:
    if isinstance(column, int):
        if column < 0 or column >= frame.shape[1]:
            raise ValueError(f"column index out of range: {column}")
        return column
    if column in frame.columns:
        return list(frame.columns).index(column)
    lowered = [str(c).lower() for c in frame.columns]
    if column.lower() in lowered:
        return lowered.index(column.lower())
    raise ValueError(f"column not found: {column}")


def _find_named_index(names: list[str], tokens: tuple[str, ...]) -> int | None:
    for idx, name in enumerate(names):
        if any(token in name for token in tokens):
            return idx
    return None


def _infer_wavelength_column(frame: pd.DataFrame) -> int:
    best_idx = 0
    best_score = -np.inf
    for idx in range(frame.shape[1]):
        values = frame.iloc[:, idx].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if len(finite) < 2:
            continue
        diffs = np.diff(finite)
        monotonic_fraction = max(np.mean(diffs > 0), np.mean(diffs < 0))
        span = np.nanmax(finite) - np.nanmin(finite)
        in_oes_range = 100 <= np.nanmedian(finite) <= 1100
        score = monotonic_fraction * 2.0 + (1.0 if in_oes_range else 0.0) + min(span / 1000.0, 1.0)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx
