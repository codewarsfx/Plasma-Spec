"use client";

import dynamic from "next/dynamic";
import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listResults } from "@/lib/api";
import { flattenFitResult } from "@/lib/plotting";
import type { FitResult } from "@/lib/types";
import { useThemePalette } from "@/lib/useThemePalette";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as any;

export function DashboardComparison() {
  const palette = useThemePalette();
  const [results, setResults] = useState<FitResult[]>([]);
  const [xKey, setXKey] = useState("metadata_uniform_frequency_khz");
  const [yKey, setYKey] = useState("total_fwhm_nm");
  const [groupKey, setGroupKey] = useState("metadata_pulse_mode");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setResults(await listResults());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load dashboard results");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const rows = useMemo(() => results.map(flattenFitResult), [results]);
  const keys = useMemo(() => Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).sort(), [rows]);
  const numericKeys = keys.filter((key) => rows.some((row) => typeof row[key] === "number"));
  const groupKeys = ["", ...keys.filter((key) => rows.some((row) => row[key] != null))];
  const plotData = useMemo(() => buildPlotData(rows, xKey, yKey, groupKey), [groupKey, rows, xKey, yKey]);

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <section className="panel p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Comparison</h2>
          <button className="icon-button" title="Refresh results" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="grid gap-3">
          <label className="grid gap-1">
            <span className="control-label">X axis</span>
            <select className="field" value={xKey} onChange={(event) => setXKey(event.target.value)}>
              {keys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1">
            <span className="control-label">Y axis</span>
            <select className="field" value={yKey} onChange={(event) => setYKey(event.target.value)}>
              {numericKeys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1">
            <span className="control-label">Group</span>
            <select className="field" value={groupKey} onChange={(event) => setGroupKey(event.target.value)}>
              {groupKeys.map((key) => (
                <option key={key} value={key}>
                  {key || "none"}
                </option>
              ))}
            </select>
          </label>
          <div className="border border-line bg-slate-50 px-3 py-2 text-sm text-slate-700" style={{ borderRadius: 6 }}>
            {rows.length} result row{rows.length === 1 ? "" : "s"}
          </div>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </div>
      </section>
      <section className="panel overflow-hidden">
        <Plot
          data={plotData}
          layout={{
            height: 560,
            margin: { l: 70, r: 30, t: 35, b: 70 },
            paper_bgcolor: palette.paper,
            plot_bgcolor: palette.plot,
            font: { color: palette.text },
            xaxis: { title: xKey, gridcolor: palette.grid, zeroline: false },
            yaxis: { title: yKey, gridcolor: palette.grid, zeroline: false },
            legend: { orientation: "h", x: 0, y: 1.1 },
            hovermode: "closest",
          }}
          config={{
            responsive: true,
            displaylogo: false,
            toImageButtonOptions: {
              format: "png",
              filename: "plasma-spec-dashboard",
              height: 560,
              width: 980,
              scale: 2,
            },
          }}
          style={{ width: "100%", height: 560 }}
          useResizeHandler
        />
      </section>
    </div>
  );
}

function buildPlotData(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string,
  groupKey: string,
) {
  const groups = new Map<string, Array<Record<string, unknown>>>();
  rows.forEach((row) => {
    if (typeof row[yKey] !== "number") return;
    const group = groupKey ? String(row[groupKey] ?? "ungrouped") : "all";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)?.push(row);
  });
  return Array.from(groups.entries()).map(([group, groupRows]) => ({
    type: "scatter",
    mode: "markers+lines",
    name: group,
    x: groupRows.map((row) => row[xKey] as string | number),
    y: groupRows.map((row) => row[yKey] as number),
    text: groupRows.map((row) => row.filename as string),
    marker: { size: 8 },
    line: { width: 1 },
    hovertemplate: "%{text}<br>x %{x}<br>y %{y:.4g}<extra>%{fullData.name}</extra>",
  }));
}
