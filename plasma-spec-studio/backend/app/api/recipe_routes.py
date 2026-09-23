"""Recipe CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthedUser, authenticated
from app.schemas.recipe_schema import Recipe
from app.services.recipe_service import delete_recipe, list_recipes, save_recipe


router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.post("")
def save_recipe_route(recipe: Recipe, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        return save_recipe(recipe.model_dump(exclude_none=True))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_recipe_route(user: AuthedUser = Depends(authenticated)) -> list[dict]:
    return list_recipes()


@router.delete("/{recipe_id}")
def delete_recipe_route(recipe_id: str, user: AuthedUser = Depends(authenticated)) -> dict:
    try:
        delete_recipe(recipe_id)
        return {"deleted": recipe_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

