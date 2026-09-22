"""Batch analysis routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.fitting_schema import BatchRunRequest
from app.services.batch_manager import get_batch, list_batches, start_batch, subscribe, unsubscribe
from app.services.batch_service import run_batch
from app.services.recipe_service import get_recipe


router = APIRouter(prefix="/api/batch", tags=["batch"])


@router.post("/run")
def run_batch_route(request: BatchRunRequest) -> dict:
    """Run a batch synchronously and return the full envelope.

    Kept for back-compat with the original frontend. For long molecular runs,
    prefer ``/api/batch/start`` + ``/api/batch/{batch_id}/stream``.
    """

    try:
        recipe = request.recipe or get_recipe(request.recipe_id)  # type: ignore[arg-type]
        return run_batch(request.spectrum_ids, recipe)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start_batch_route(request: BatchRunRequest) -> dict:
    """Start a batch in the background and return its identifier.

    Open ``/api/batch/{batch_id}/stream`` (SSE) for per-spectrum progress
    events, or poll ``/api/batch/{batch_id}/result`` for the final envelope.
    """

    try:
        recipe = request.recipe or get_recipe(request.recipe_id)  # type: ignore[arg-type]
        state = start_batch(request.spectrum_ids, recipe)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "batch_id": state.batch_id,
        "total": state.total,
        "recipe_kind": state.recipe_kind,
    }


@router.get("/{batch_id}/stream")
async def batch_stream_route(batch_id: str) -> StreamingResponse:
    """Server-Sent Events stream of per-spectrum progress events."""

    try:
        state = get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_generator():
        queue = await subscribe(state)
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in {"finished", "error"}:
                    break
        finally:
            unsubscribe(state, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable buffering at the reverse proxy
        },
    )


@router.get("/{batch_id}/result")
def batch_result_route(batch_id: str) -> dict:
    try:
        state = get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not state.finished:
        raise HTTPException(
            status_code=202,
            detail={
                "batch_id": state.batch_id,
                "completed": state.completed,
                "failed": state.failed,
                "total": state.total,
            },
        )
    if state.error:
        raise HTTPException(status_code=500, detail=state.error)
    assert state.result is not None
    return state.result


@router.get("")
def list_batches_route() -> dict:
    return {"batches": list_batches()}

