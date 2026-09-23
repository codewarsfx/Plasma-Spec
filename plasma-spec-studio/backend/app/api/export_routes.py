"""Export and result routes."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import AuthedUser, authenticated
from app.schemas.fitting_schema import ExportResultRequest, ReportRequest
from app.services.export_service import export_fit_plot_png, export_result_csv, export_result_json
from app.services.report_service import export_report_html, export_report_pdf
from app.services.spectrum_service import get_export_bytes, list_fit_results


router = APIRouter(prefix="/api", tags=["exports"])


@router.post("/exports/result")
def export_result(request: ExportResultRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    exports = {}
    try:
        if "json" in request.formats:
            exports["json"] = export_result_json(request.result)
        if "csv" in request.formats:
            exports["csv"] = export_result_csv(request.result)
        if "png" in request.formats:
            exports["png"] = export_fit_plot_png(request.result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"exports": exports}


@router.post("/reports/result")
def export_report(request: ReportRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    """Render a per-result HTML and/or PDF report and return download links."""

    exports = {}
    try:
        if "html" in request.formats:
            exports["html"] = export_report_html(request.result)
        if "pdf" in request.formats:
            exports["pdf"] = export_report_pdf(request.result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not exports:
        raise HTTPException(status_code=400, detail="no formats requested")
    return {"exports": exports}


@router.get("/exports/{export_id}")
def download_export(export_id: str, user: AuthedUser = Depends(authenticated)) -> Response:
    try:
        content, filename = get_export_bytes(export_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=content_type,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/results")
def results_for_dashboard(user: AuthedUser = Depends(authenticated)) -> list[dict]:
    return list_fit_results()

