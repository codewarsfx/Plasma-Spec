"""Recipe persistence for repeatable preprocessing and fitting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.spectrum_service import _connect, initialize_storage


def save_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Create or update a serialized fitting recipe."""

    initialize_storage()
    recipe_id = recipe.get("id") or str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    recipe = {**recipe, "id": recipe_id}
    with _connect() as conn:
        existing = conn.execute("SELECT created_at FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO recipes
            (id, name, diagnostic, recipe_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                recipe_id,
                recipe.get("name", "Untitled recipe"),
                recipe.get("diagnostic", "analysis"),
                json.dumps(recipe),
                created_at,
                now,
            ),
        )
    return recipe


def list_recipes() -> list[dict[str, Any]]:
    initialize_storage()
    with _connect() as conn:
        rows = conn.execute("SELECT recipe_json FROM recipes ORDER BY updated_at DESC").fetchall()
    return [json.loads(row["recipe_json"]) for row in rows]


def get_recipe(recipe_id: str) -> dict[str, Any]:
    initialize_storage()
    with _connect() as conn:
        row = conn.execute("SELECT recipe_json FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise KeyError(f"recipe not found: {recipe_id}")
    return json.loads(row["recipe_json"])


def delete_recipe(recipe_id: str) -> None:
    initialize_storage()
    with _connect() as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))

