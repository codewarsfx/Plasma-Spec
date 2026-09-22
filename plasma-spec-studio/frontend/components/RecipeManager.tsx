"use client";

import { Download, FileJson, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { deleteRecipe, listRecipes } from "@/lib/api";
import type { Recipe } from "@/lib/types";

type RecipeManagerProps = {
  onSelect?: (recipe: Recipe) => void;
};

export function RecipeManager({ onSelect }: RecipeManagerProps) {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setRecipes(await listRecipes());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load recipes");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function selectRecipe(id: string) {
    setSelected(id);
    const recipe = recipes.find((item) => item.id === id);
    if (recipe) onSelect?.(recipe);
  }

  async function removeSelected() {
    if (!selected) return;
    await deleteRecipe(selected);
    setSelected("");
    refresh();
  }

  const current = recipes.find((item) => item.id === selected);

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Recipes</h2>
        <button className="icon-button" title="Refresh recipes" onClick={refresh}>
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      <div className="grid gap-3">
        <label className="grid gap-1">
          <span className="control-label">Saved recipe</span>
          <select className="field" value={selected} onChange={(event) => selectRecipe(event.target.value)}>
            <option value="">Select recipe</option>
            {recipes.map((recipe) => (
              <option key={recipe.id} value={recipe.id}>
                {recipe.name}
              </option>
            ))}
          </select>
        </label>
        {current ? (
          <div className="border border-line bg-slate-50 p-3 text-xs text-slate-700" style={{ borderRadius: 6 }}>
            <div className="font-semibold text-ink">{current.recipe_kind ?? current.diagnostic}</div>
            {current.window_nm ? (
              <div>{current.window_nm[0]}-{current.window_nm[1]} nm</div>
            ) : null}
            <div>{(current.preprocessing ?? []).length} preprocessing step(s)</div>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {current ? (
            <a
              className="text-button"
              href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(current, null, 2))}`}
              download={`${current.name.replace(/\s+/g, "_")}.json`}
            >
              <FileJson className="h-4 w-4" />
              JSON
            </a>
          ) : (
            <button className="text-button" disabled>
              <Download className="h-4 w-4" />
              JSON
            </button>
          )}
          <button className="text-button" onClick={removeSelected} disabled={!selected}>
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        </div>
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
      </div>
    </section>
  );
}

