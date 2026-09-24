"""Activity feed routes (sharing fit results with other members)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import AuthedUser, authenticated
from app.services.share_service import delete_shared_result, list_shared_results, share_result


router = APIRouter(prefix="/api/share", tags=["share"])


class ShareResultRequest(BaseModel):
    result: dict[str, Any]
    caption: str | None = None


@router.post("")
def share_result_route(request: ShareResultRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        return share_result(request.result, request.caption)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_shared_results_route(limit: int = 50, user: AuthedUser = Depends(authenticated)) -> dict:
    return {"results": list_shared_results(limit)}


@router.delete("/{share_id}")
def delete_shared_result_route(share_id: str, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        delete_shared_result(share_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": share_id}
