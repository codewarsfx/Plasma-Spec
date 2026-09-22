"""Fitting and analysis routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.fitting_schema import (
    AtomicForwardFitRequest,
    ElectronDensityRequest,
    FitResultResponse,
    HbetaFitRequest,
    LineIdentificationRequest,
    MolecularFitRequest,
    PeakAreaRequest,
    PeakListRequest,
    StateByStateMolecularFitRequest,
    UnifiedMolecularFitRequest,
)
from app.services.fitting_service import (
    analyze_peak_by_id,
    analyze_peak_list_by_id,
    compute_electron_density_by_id,
    fit_atomic_forward_by_id,
    fit_hbeta_by_id,
    fit_molecular_by_id,
    fit_molecular_state_by_state_by_id,
    fit_n2_by_id,
    fit_oh_by_id,
    identify_lines_by_id,
)


router = APIRouter(prefix="/api", tags=["fitting"])


@router.post("/fit/hbeta", response_model=FitResultResponse)
def fit_hbeta_route(request: HbetaFitRequest) -> dict:
    try:
        return fit_hbeta_by_id(request.spectrum_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fit/oh", response_model=FitResultResponse)
def fit_oh_route(request: MolecularFitRequest) -> dict:
    try:
        data = request.model_dump()
        if not data.get("window_nm"):
            data["window_nm"] = (306.0, 312.0)
        return fit_oh_by_id(request.spectrum_id, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fit/n2", response_model=FitResultResponse)
def fit_n2_route(request: MolecularFitRequest) -> dict:
    try:
        data = request.model_dump()
        if not data.get("window_nm"):
            data["window_nm"] = (334.0, 339.0)
        return fit_n2_by_id(request.spectrum_id, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fit/molecular", response_model=FitResultResponse)
def fit_molecular_route(request: UnifiedMolecularFitRequest) -> dict:
    """Unified molecular fit for any species in the SQLite registry."""

    try:
        data = request.model_dump()
        return fit_molecular_by_id(request.spectrum_id, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fit/molecular/state-by-state", response_model=FitResultResponse)
def fit_molecular_state_by_state_route(request: StateByStateMolecularFitRequest) -> dict:
    """Temperature-independent molecular state-population fit."""

    try:
        data = request.model_dump()
        return fit_molecular_state_by_state_by_id(request.spectrum_id, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fit/atomic-forward", response_model=FitResultResponse)
def fit_atomic_forward_route(request: AtomicForwardFitRequest) -> dict:
    """Relative NIST-backed atomic forward model."""

    try:
        data = request.model_dump()
        return fit_atomic_forward_by_id(request.spectrum_id, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostics/electron-density", response_model=FitResultResponse)
def electron_density_route(request: ElectronDensityRequest) -> dict:
    """H-alpha (Gigosos) electron density - port of the lab MATLAB workflow."""

    try:
        return compute_electron_density_by_id(request.spectrum_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze/peak-area", response_model=FitResultResponse)
def peak_area_route(request: PeakAreaRequest) -> dict:
    try:
        return analyze_peak_by_id(request.spectrum_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze/peak-list")
def peak_list_route(request: PeakListRequest) -> dict:
    try:
        return analyze_peak_list_by_id(request.spectrum_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/identify-lines")
def identify_lines_route(request: LineIdentificationRequest) -> dict:
    try:
        return identify_lines_by_id(request.spectrum_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
