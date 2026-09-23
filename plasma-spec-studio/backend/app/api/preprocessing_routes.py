"""Preprocessing routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthedUser, authenticated
from app.preprocessing.pipeline import apply_preprocessing_operations
from app.schemas.spectrum_schema import PreprocessRequest, PreprocessResponse
from app.services.export_service import export_processed_spectrum_csv
from app.services.spectrum_service import get_spectrum, save_spectrum


router = APIRouter(prefix="/api", tags=["preprocessing"])


@router.post("/preprocess", response_model=PreprocessResponse)
def preprocess_spectrum(request: PreprocessRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        spectrum = get_spectrum(request.spectrum_id)
        background = get_spectrum(request.background_spectrum_id) if request.background_spectrum_id else None
        processed = apply_preprocessing_operations(
            spectrum,
            [operation.model_dump() for operation in request.operations],
            background=background,
        )
        mode = "preview"
        if request.save_as_new:
            save_spectrum(processed)
            mode = "saved"
        return {"spectrum": processed.to_dict(include_arrays=True), "mode": mode}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preprocess/export-csv")
def export_processed(request: PreprocessRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        spectrum = get_spectrum(request.spectrum_id)
        processed = apply_preprocessing_operations(
            spectrum,
            [operation.model_dump() for operation in request.operations],
        )
        return export_processed_spectrum_csv(processed)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

