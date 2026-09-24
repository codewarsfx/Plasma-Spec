"""Activity feed (sharing fit results with other members).

Thin backend-agnostic facade -- see ``spectrum_service.py``'s module
docstring for how the active ``Store`` is selected.
"""

from __future__ import annotations

from typing import Any

from app.services.backends.base import get_current_store


def share_result(result: dict[str, Any], caption: str | None) -> dict[str, Any]:
    return get_current_store().share_result(result, caption)


def list_shared_results(limit: int = 50) -> list[dict[str, Any]]:
    return get_current_store().list_shared_results(limit)


def delete_shared_result(share_id: str) -> None:
    get_current_store().delete_shared_result(share_id)
