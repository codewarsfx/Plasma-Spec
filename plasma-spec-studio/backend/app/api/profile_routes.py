"""Profile (display name + avatar) routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.auth import AuthedUser, authenticated
from app.services.profile_service import get_avatar_bytes, get_profile, save_avatar, update_profile


router = APIRouter(prefix="/api/profile", tags=["profile"])

MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2MB


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


@router.get("")
def get_profile_route(user: AuthedUser = Depends(authenticated)) -> dict:
    return get_profile()


@router.put("")
def update_profile_route(request: UpdateProfileRequest, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        return update_profile(request.display_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/avatar")
async def upload_avatar_route(
    file: Annotated[UploadFile, File(description="Avatar image (PNG/JPEG/WebP, up to 2MB)")],
    user: AuthedUser = Depends(authenticated),
) -> dict:
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="avatar must be an image file")
    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="avatar must be 2MB or smaller")
    try:
        avatar_url = save_avatar(content, file.content_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"avatar_url": avatar_url, **get_profile()}


@router.get("/avatar")
def download_avatar_route(user: AuthedUser = Depends(authenticated)) -> Response:
    # Only meaningful in local mode -- Supabase's avatar_url from
    # GET /api/profile is already a direct public Storage URL the frontend
    # uses as-is, so this route is never hit in that mode.
    try:
        content, content_type = get_avatar_bytes()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=content, media_type=content_type)
