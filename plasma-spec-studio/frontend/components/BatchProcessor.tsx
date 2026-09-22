"use client";

import { Loader2, Play, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  batchStreamUrl,
  exportUrl,
  getBatchResult,
  listRecipes,
  listSpectra,
  startBatchStreamed,
} from "@/lib/api";
import { toast } from "@/components/Toast";
import type { BatchRunResult, Recipe, SpectrumSummary } from "@/lib/types";

type BatchProgress = {
  status: "idle" | "running" | "finished" | "error";
  total: number;
  completed: number;
  failed: number;
  message?: string;
  recipeName?: string;
  startedAt?: number;
};

export function BatchProcessor() {
  const [spectra, setSpectra] = useState<SpectrumSummary[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedSpectra, setSelectedSpectra] = useState<Set<string>>(new Set());
  const [recipeId, setRecipeId] = useState("");
  const [result, setResult] = useState<BatchRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<BatchProgress>({
    status: "idle",
    total: 0,
    completed: 0,
    failed: 0,
  });
  const eventSourceRef = useRef<EventSource | null>(null);

  async function refresh() {
    setError(null);
    try {
      const [nextSpectra, nextRecipes] = await Promise.all([listSpectra(), listRecipes()]);
      setSpectra(nextSpectra);
      setRecipes(nextRecipes);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Batch data load failed");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const recipe = useMemo(() => recipes.find((item) => item.id === recipeId), [recipeId, recipes]);
  const selectedCount = selectedSpectra.size;

  function toggleSpectrum(id: string, checked: boolean) {
    const next = new Set(selectedSpectra);
    if (checked) next.add(id);
    else next.delete(id);
    setSelectedSpectra(next);
  }

  async function startBatch() {
    if (!recipe) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setProgress({
      status: "running",
      total: selectedSpectra.size,
      completed: 0,
      failed: 0,
      recipeName: recipe.name,
      startedAt: Date.now(),
    });

    try {
      const { batch_id, total } = await startBatchStreamed(
        Array.from(selectedSpectra),
        recipe,
      );
      // Subscribe to live progress
      const source = new EventSource(batchStreamUrl(batch_id));
      eventSourceRef.current = source;
      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          const type = data.type as string;
          if (type === "started") {
            setProgress((p) => ({ ...p, total: (data.total as number) ?? total }));
          } else if (type === "progress") {
            setProgress((p) => ({
              ...p,
              completed: (data.completed as number) ?? p.completed,
              failed: (data.failed as number) ?? p.failed,
              message: `${(data.spectrum_id as string)?.slice(0, 8) ?? "?"} ${
                data.status === "failed" ? "failed" : "done"
              }`,
            }));
          } else if (type === "finished") {
            setProgress((p) => ({
              ...p,
              status: "finished",
              completed: (data.completed as number) ?? p.completed,
              failed: (data.failed as number) ?? p.failed,
              message: `elapsed ${
                ((data.elapsed_seconds as number) ?? 0).toFixed(1)
              } s`,
            }));
            // Fetch the full result envelope
            getBatchResult(batch_id)
              .then((envelope) => {
                setResult(envelope);
                toast.success(
                  `Batch complete`,
                  `${envelope.completed} ok / ${envelope.failed} failed`,
                );
              })
              .catch((exc) => {
                setError(exc instanceof Error ? exc.message : "result fetch failed");
              });
            source.close();
            setBusy(false);
          } else if (type === "error") {
            setProgress((p) => ({
              ...p,
              status: "error",
              message: data.error as string,
            }));
            setError(data.error as string);
            toast.error("Batch failed", data.error as string);
            source.close();
            setBusy(false);
          }
        } catch (exc) {
          console.error("batch stream parse error", exc);
        }
      };
      source.onerror = () => {
        // EventSource auto-reconnects; only show an error if we never got a
        // finished event.
        if (eventSourceRef.current === source && progress.status !== "finished") {
          // Don't tear down here - let the server's finished event close it.
        }
      };
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Batch start failed");
      setProgress((p) => ({ ...p, status: "error" }));
      setBusy(false);
    }
  }

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const csvExport = result?.exports?.csv;
  const xlsxExport = result?.exports?.xlsx;

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <section className="panel p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Batch Setup</h2>
          <button className="icon-button" title="Refresh" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="grid gap-3">
          <label className="grid gap-1">
            <span className="control-label">Recipe</span>
            <select className="field" value={recipeId} onChange={(event) => setRecipeId(event.target.value)}>
              <option value="">Select recipe</option>
              {recipes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="control-label">Spectra</span>
              <span className="text-xs text-slate-500">{selectedCount} selected</span>
            </div>
            <div className="max-h-80 overflow-auto border border-line" style={{ borderRadius: 6 }}>
              {spectra.map((spectrum) => (
                <label
                  key={spectrum.id}
                  className="flex items-center gap-2 border-b border-line px-3 py-2 text-sm last:border-b-0"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-teal-700"
                    checked={selectedSpectra.has(spectrum.id)}
                    onChange={(event) => toggleSpectrum(spectrum.id, event.target.checked)}
                  />
                  <span className="truncate">{spectrum.filename}</span>
                </label>
              ))}
              {spectra.length === 0 ? <div className="px-3 py-6 text-sm text-slate-500">No spectra</div> : null}
            </div>
          </div>
          <button className="primary-button" onClick={startBatch} disabled={!recipe || selectedCount === 0 || busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run Batch
          </button>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">Batch Results</h2>
          {csvExport?.export_id ? (
            <a className="text-button" href={exportUrl(csvExport.export_id)}>
              CSV
            </a>
          ) : null}
          {xlsxExport?.export_id ? (
            <a className="text-button" href={exportUrl(xlsxExport.export_id)}>
              XLSX
            </a>
          ) : null}
        </div>
        <div className="grid grid-cols-3 border-b border-line bg-slate-50 text-center text-sm">
          <div className="border-r border-line px-3 py-2">
            <div className="text-xs uppercase tracking-normal text-slate-500">Total</div>
            <div className="text-lg font-semibold">
              {result ? result.completed + result.failed : progress.total || 0}
            </div>
          </div>
          <div className="border-r border-line px-3 py-2">
            <div className="text-xs uppercase tracking-normal text-slate-500">Completed</div>
            <div className="text-lg font-semibold text-teal-800">
              {result?.completed ?? progress.completed}
            </div>
          </div>
          <div className="px-3 py-2">
            <div className="text-xs uppercase tracking-normal text-slate-500">Failed</div>
            <div className="text-lg font-semibold text-red-800">
              {result?.failed ?? progress.failed}
            </div>
          </div>
        </div>

        {progress.status === "running" || progress.status === "finished" || progress.status === "error" ? (
          <div className="border-b border-line px-4 py-3">
            <div className="mb-1.5 flex items-center justify-between gap-2 text-xs text-slate-600">
              <span>
                {progress.status === "running"
                  ? `Running ${progress.recipeName ?? "batch"}…`
                  : progress.status === "finished"
                    ? `Finished ${progress.recipeName ?? "batch"}`
                    : `Batch error`}
                {progress.message ? ` · ${progress.message}` : ""}
              </span>
              <span className="tabular-nums">
                {progress.completed + progress.failed} / {progress.total}
                {progress.startedAt
                  ? ` · ${((Date.now() - progress.startedAt) / 1000).toFixed(1)} s`
                  : ""}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded bg-slate-200">
              <div
                className={`h-full transition-all ${
                  progress.status === "error" ? "bg-red-500" : "bg-plasma"
                }`}
                style={{
                  width: `${
                    progress.total > 0
                      ? Math.min(
                          100,
                          ((progress.completed + progress.failed) / progress.total) * 100,
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
        ) : null}
        <div className="max-h-[560px] overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white">
              <tr>
                {columns(result).map((column) => (
                  <th key={column} className="border-b border-line px-2 py-2">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result?.rows?.map((row, index) => (
                <tr key={index} className="odd:bg-slate-50">
                  {columns(result).map((column) => (
                    <td key={column} className="border-b border-line px-2 py-1.5">
                      {String(row[column] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!result ? <div className="px-4 py-10 text-center text-sm text-slate-500">No batch output</div> : null}
        </div>
      </section>
    </div>
  );
}

function columns(result: BatchRunResult | null) {
  if (!result?.rows?.length) {
    return ["filename", "diagnostic", "fit_quality", "warnings"];
  }
  const preferred = ["filename", "diagnostic", "fit_quality", "warnings", "error"];
  const all = Array.from(new Set(result.rows.flatMap((row) => Object.keys(row))));
  return [...preferred.filter((key) => all.includes(key)), ...all.filter((key) => !preferred.includes(key))];
}

