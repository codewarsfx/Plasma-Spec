"use client";

import { useState } from "react";
import { LegacyPageShell } from "@/components/LegacyPageShell";
import { RecipeEditor } from "@/components/RecipeEditor";
import { RecipeManager } from "@/components/RecipeManager";
import type { Recipe } from "@/lib/types";

export default function RecipesPage() {
  const [selected, setSelected] = useState<Recipe | undefined>(undefined);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <LegacyPageShell
      title="Recipes"
      description="Save and edit reusable analysis configurations: peak lists, molecular fits, electron density."
    >
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <RecipeManager
          key={refreshKey}
          onSelect={(recipe) => setSelected(recipe)}
        />
        <div className="grid gap-4">
          <RecipeEditor
            key={selected?.id ?? "new"}
            initial={selected}
            onSaved={() => setRefreshKey((k) => k + 1)}
          />
        </div>
      </div>
    </LegacyPageShell>
  );
}
