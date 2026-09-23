"""Recipe persistence for repeatable preprocessing and fitting.

Thin backend-agnostic facade -- see ``spectrum_service.py``'s module
docstring for how the active ``Store`` is selected.
"""

from __future__ import annotations

from typing import Any

from app.services.backends.base import get_current_store


def save_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Create or update a serialized fitting recipe."""

    return get_current_store().save_recipe(recipe)


def list_recipes() -> list[dict[str, Any]]:
    return get_current_store().list_recipes()


def get_recipe(recipe_id: str) -> dict[str, Any]:
    return get_current_store().get_recipe(recipe_id)


def delete_recipe(recipe_id: str) -> None:
    get_current_store().delete_recipe(recipe_id)
