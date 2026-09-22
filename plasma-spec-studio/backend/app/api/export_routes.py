"""Export and result routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.fitting_schema import ExportResultRequest, ReportRequest
from app.services.export_service import export_fit_plot_png, export_result_csv, export_result_json
from app.services.report_service import export_report_html, export_report_pdf
from app.services.spectrum_service import get_export_path, list_fit_results


router = APIRouter(prefix="/api", tags=["exports"])


@router.post("/exports/result")
def export_result(request: ExportResultRequest) -> dict:
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
def export_report(request: ReportRequest) -> dict:
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
def download_export(export_id: str) -> FileResponse:
    try:
        path = get_export_path(export_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.get("/results")
def results_for_dashboard() -> list[dict]:
    return list_fit_results()

