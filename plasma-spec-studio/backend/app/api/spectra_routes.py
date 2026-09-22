"""Spectrum import and retrieval routes."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.preprocessing.importers import load_metadata_csv
from app.schemas.spectrum_schema import SpectrumResponse, SpectrumSummary
from app.services.spectrum_service import get_spectrum, list_spectra, save_uploaded_spectrum


router = APIRouter(prefix="/api/spectra", tags=["spectra"])


@router.post("/upload", response_model=list[SpectrumSummary])
async def upload_spectra(
    files: Annotated[list[UploadFile], File()],
    metadata_json: Annotated[str | None, Form()] = None,
    wavelength_column: Annotated[str | None, Form()] = None,
    intensity_column: Annotated[str | None, Form()] = None,
    filename_pattern: Annotated[str | None, Form()] = None,
    parse_filename_metadata: Annotated[bool, Form()] = True,
) -> list[dict]:
    """Upload one or more spectra.

    ``parse_filename_metadata`` (default true) merges experimental metadata
    parsed from the filename (pulse frequency, burst period, cycles, replicate)
    into the spectrum record. ``filename_pattern`` overrides the default tag
    matchers with a user-supplied regex (named groups become metadata keys).
    """

    metadata = json.loads(metadata_json) if metadata_json else {}
    saved = []
    for file in files:
        try:
            spectrum = save_uploaded_spectrum(
                await file.read(),
                filename=file.filename or "uploaded_spectrum",
                metadata=metadata,
                wavelength_column=_parse_column_override(wavelength_column),
                intensity_column=_parse_column_override(intensity_column),
                filename_pattern=filename_pattern,
                parse_filename_metadata=parse_filename_metadata,
            )
            saved.append(spectrum.to_dict(include_arrays=False))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc
    return saved


@router.get("", response_model=list[SpectrumSummary])
def list_spectrum_records() -> list[dict]:
    return list_spectra()


@router.get("/{spectrum_id}", response_model=SpectrumResponse)
def read_spectrum(spectrum_id: str) -> dict:
    try:
        return get_spectrum(spectrum_id).to_dict(include_arrays=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _parse_column_override(value: str | None) -> str | int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return value

