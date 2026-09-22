from __future__ import annotations

import io

import pandas as pd
import pytest

from app.preprocessing.importers import (
    load_spectrum_excel,
    load_spectrum_file,
    load_spectrum_text,
)


def test_load_csv_with_headers(tmp_path):
    path = tmp_path / "spectrum.csv"
    path.write_text("wavelength_nm,intensity\n484.0,10\n486.0,50\n488.0,12\n")

    spectrum = load_spectrum_file(path)

    assert spectrum.filename == "spectrum.csv"
    assert spectrum.wavelength_nm.tolist() == [484.0, 486.0, 488.0]
    assert spectrum.intensity.tolist() == [10.0, 50.0, 12.0]


def test_load_csv_without_headers():
    spectrum = load_spectrum_text("484 10\n486 50\n488 12\n", filename="plain.txt")

    assert spectrum.wavelength_nm.tolist() == [484.0, 486.0, 488.0]
    assert spectrum.intensity.tolist() == [10.0, 50.0, 12.0]


def test_detect_columns_from_names():
    text = "counts,nm,other\n10,484,1\n50,486,1\n12,488,1\n"

    spectrum = load_spectrum_text(text)

    assert spectrum.wavelength_nm.tolist() == [484.0, 486.0, 488.0]
    assert spectrum.intensity.tolist() == [10.0, 50.0, 12.0]


def test_bad_file_raises_user_friendly_error():
    with pytest.raises(ValueError, match="could not find|enough finite"):
        load_spectrum_text("not a spectrum\nstill not a spectrum\n")


def _build_avantes_style_xlsx(tmp_path):
    """Write a small Avantes-style sheet: 6 header rows then numeric pairs."""

    path = tmp_path / "avantes.xlsx"
    rows = [
        ("Filename-->", None),
        ("Mode/Unit-->", None),
        ("Int.time[ms]-->", 5000),
        ("NrOfAverages-->", 3),
        ("Smoothing-->", 0),
        ("Wavelength [nm]", None),
    ]
    rows.extend((300.0 + 0.5 * i, 100.0 + i * i) for i in range(20))
    frame = pd.DataFrame(rows)
    frame.to_excel(path, header=False, index=False)
    return path


def test_load_excel_skips_header_metadata_and_parses_columns(tmp_path):
    path = _build_avantes_style_xlsx(tmp_path)
    spectrum = load_spectrum_excel(path)
    assert spectrum.wavelength_nm.tolist() == [300.0 + 0.5 * i for i in range(20)]
    assert spectrum.intensity.tolist() == [100.0 + i * i for i in range(20)]
    assert spectrum.metadata["int.time[ms]"] == 5000
    assert spectrum.metadata["nrofaverages"] == 3
    assert spectrum.metadata["smoothing"] == 0


def test_load_excel_dispatches_through_load_spectrum_file(tmp_path):
    path = _build_avantes_style_xlsx(tmp_path)
    spectrum = load_spectrum_file(path)
    assert spectrum.filename.endswith(".xlsx")
    assert len(spectrum.wavelength_nm) == 20


def test_load_excel_from_bytes_uses_supplied_filename(tmp_path):
    path = _build_avantes_style_xlsx(tmp_path)
    data = path.read_bytes()
    spectrum = load_spectrum_excel(data, filename="upload.xlsx")
    assert spectrum.filename == "upload.xlsx"
    assert len(spectrum.wavelength_nm) == 20


def test_load_excel_rejects_sheet_without_numeric_columns(tmp_path):
    path = tmp_path / "junk.xlsx"
    pd.DataFrame([["only", "text"], ["here", "too"]]).to_excel(path, header=False, index=False)
    with pytest.raises(ValueError):
        load_spectrum_excel(path)

