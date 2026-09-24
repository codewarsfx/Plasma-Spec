"""Profile (display name + avatar) persistence.

Thin backend-agnostic facade -- see ``spectrum_service.py``'s module
docstring for how the active ``Store`` is selected.
"""

from __future__ import annotations

from typing import Any

from app.services.backends.base import get_current_store


def get_profile() -> dict[str, Any]:
    return get_current_store().get_profile()


def update_profile(display_name: str | None) -> dict[str, Any]:
    return get_current_store().update_profile(display_name)


def save_avatar(content: bytes, content_type: str) -> str:
    return get_current_store().save_avatar(content, content_type)


def get_avatar_bytes() -> tuple[bytes, str]:
    return get_current_store().get_avatar_bytes()
