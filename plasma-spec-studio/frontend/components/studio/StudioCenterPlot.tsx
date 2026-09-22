"use client";

import { AlertTriangle, Crosshair, FlaskConical } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { searchAtomicLines } from "@/lib/api";
import type { AtomicLine, FitResult, PreprocessingOperation, Spectrum } from "@/lib/types";
import { useThemePalette } from "@/lib/useThemePalette";
import type { StudioPlotTab } from "./types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as any;

type StudioCenterPlotProps = {
  primary: Spectrum | null;
  overlays: Spectrum[];
  preprocessed: Spectrum | null;
  baselineCurve?: Array<{ wavelength_nm: number; value: number }> | null;
  fitResult: FitResult | null;
  activePlotTab: StudioPlotTab;
  onChangePlotTab: (tab: StudioPlotTab) => void;
  windowNm: [number, number];
  onSelectRegion: (range: [number, number]) => void;
  preprocessing: PreprocessingOperation[];
  selectedTool: string;
};

const OVERLAY_COLORS = ["#0066ff", "#4338ca", "#b7791f", "#be123c", "#0369a1", "#166534"];

export function StudioCenterPlot({
  primary,
  overlays,
  preprocessed,
  fitResult,
  activePlotTab,
  onChangePlotTab,
  windowNm,
  onSelectRegion,
  preprocessing,
  selectedTool,
}: StudioCenterPlotProps) {
  const palette = useThemePalette();
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [nearestLine, setNearestLine] = useState<AtomicLine | null>(null);
  const overlayColors = useMemo(
    () => palette.theme === "dark"
      ? ["#60a5fa", "#a5b4fc", "#fbbf24", "#fb7185", "#38bdf8", "#86efac"]
      : OVERLAY_COLORS,
    [palette.theme],
  );

  useEffect(() => {
    if (cursor === null) {
      setNearestLine(null);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(async () => {
      try {
        const response = await searchAtomicLines({
          near_nm: cursor.x,
          tolerance_nm: 0.5,
          max_results: 1,
        });
        if (!cancelled) setNearestLine(response.results[0] ?? null);
      } catch {
        if (!cancelled) setNearestLine(null);
      }
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [cursor]);

  const plotData = useMemo(() => {
    const traces: any[] = [];

    if (activePlotTab === "residuals" && fitResult?.residual_curve?.length) {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: fitResult.residual_curve.map((p) => p.wavelength_nm),
        y: fitResult.residual_curve.map((p) => p.value),
        name: "Residual",
        line: { color: palette.residual, width: 1 },
        hovertemplate: "λ %{x:.3f} nm<br>residual %{y:.4g}<extra></extra>",
      });
    } else if (activePlotTab === "baseline" && preprocessed) {
      if (primary) {
        traces.push({
          type: "scatter",
          mode: "lines",
          x: primary.wavelength_nm,
          y: primary.intensity,
          name: "Raw",
          line: { color: palette.muted, width: 1.2 },
          hovertemplate: "λ %{x:.3f} nm<br>%{y:.3g}<extra>raw</extra>",
        });
      }
      traces.push({
        type: "scatter",
        mode: "lines",
        x: preprocessed.wavelength_nm,
        y: preprocessed.intensity,
        name: "Preprocessed",
        line: { color: palette.plasma, width: 1.8 },
        hovertemplate: "λ %{x:.3f} nm<br>%{y:.3g}<extra>processed</extra>",
      });
    } else {
      // Spectrum tab: primary + overlays + (optionally) fit curve
      if (primary) {
        traces.push({
          type: "scatter",
          mode: "lines",
          x: primary.wavelength_nm,
          y: primary.intensity,
          name: primary.filename,
          line: { color: overlayColors[0], width: 1.8 },
          hovertemplate: "λ %{x:.3f} nm<br>%{y:.3g}<extra>" + primary.filename + "</extra>",
        });
      }
      overlays.forEach((spectrum, index) => {
        traces.push({
          type: "scatter",
          mode: "lines",
          x: spectrum.wavelength_nm,
          y: spectrum.intensity,
          name: spectrum.filename,
          line: {
            color: overlayColors[(index + 1) % overlayColors.length],
            width: 1.2,
            dash: "dot",
          },
          opacity: 0.85,
          hovertemplate: "λ %{x:.3f} nm<br>%{y:.3g}<extra>" + spectrum.filename + "</extra>",
        });
      });
      if (fitResult?.fit_curve?.length) {
        traces.push({
          type: "scatter",
          mode: "lines",
          x: fitResult.fit_curve.map((p) => p.wavelength_nm),
          y: fitResult.fit_curve.map((p) => p.value),
          name: "Fit",
          line: { color: palette.fit, width: 2 },
          hovertemplate: "λ %{x:.3f} nm<br>%{y:.3g}<extra>fit</extra>",
        });
      }
      if (fitResult?.measured_curve?.length && activePlotTab === "spectrum") {
        traces.push({
          type: "scatter",
          mode: "markers",
          x: fitResult.measured_curve.map((p) => p.wavelength_nm),
          y: fitResult.measured_curve.map((p) => p.value),
          name: "Fit window",
          marker: { color: palette.plasma, size: 4, opacity: 0.5 },
          showlegend: false,
          hoverinfo: "skip",
        });
      }
    }
    return traces;
  }, [activePlotTab, fitResult, overlayColors, overlays, palette, preprocessed, primary]);

  const yAxisTitle = activePlotTab === "residuals" ? "Residual (a.u.)" : "Intensity (a.u.)";

  // Clip the window-highlight rectangle to the actual data range so the auto
  // x-axis doesn't blow up when the window (e.g. the OH default 306-312 nm)
  // is far outside the data (e.g. an H-alpha-only spectrum at 595-712 nm).
  const dataMin = primary ? primary.wavelength_nm[0] : null;
  const dataMax = primary
    ? primary.wavelength_nm[primary.wavelength_nm.length - 1]
    : null;
  const windowOverlaps =
    dataMin !== null && dataMax !== null
    && windowNm[0] <= dataMax && windowNm[1] >= dataMin;
  const clippedWindow: [number, number] | null =
    windowOverlaps && dataMin !== null && dataMax !== null
      ? [Math.max(windowNm[0], dataMin), Math.min(windowNm[1], dataMax)]
      : null;
  const showWindowOverlay =
    primary != null && activePlotTab === "spectrum" && clippedWindow != null;

  // Auto-frame to the data range whenever the primary spectrum changes.
  // ``uirevision`` keyed to the spectrum filename means Plotly preserves user
  // zoom/pan within a spectrum but resets when the spectrum changes.
  const xAxisRange = primary ? [dataMin, dataMax] : undefined;
  const uirevision = primary ? `${primary.id}-${activePlotTab}` : "empty";

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-2">
        <button
          className={tabButtonClass(activePlotTab === "spectrum")}
          onClick={() => onChangePlotTab("spectrum")}
        >
          Spectrum
        </button>
        <button
          className={tabButtonClass(activePlotTab === "baseline")}
          onClick={() => onChangePlotTab("baseline")}
          disabled={preprocessing.length === 0}
          title={preprocessing.length === 0 ? "Enable preprocessing first" : "Compare raw vs processed"}
        >
          Baseline preview
        </button>
        <button
          className={tabButtonClass(activePlotTab === "residuals")}
          onClick={() => onChangePlotTab("residuals")}
          disabled={!fitResult?.residual_curve?.length}
          title={!fitResult ? "Run a fit first" : "Show residuals"}
        >
          Residuals
        </button>
        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1 whitespace-nowrap">
            <Crosshair className="h-3.5 w-3.5 text-slate-500" />
            {cursor
              ? `${cursor.x.toFixed(3)} nm · ${formatY(cursor.y)}`
              : "move cursor over plot"}
          </span>
          {nearestLine ? (
            <span
              className="inline-flex max-w-[280px] items-center gap-1 truncate border border-line bg-slate-50 px-2 py-0.5 text-[11px]"
              style={{ borderRadius: 999 }}
              title={`${nearestLine.species} ${nearestLine.wavelength_air_nm.toFixed(3)} nm`}
            >
              <FlaskConical className="h-3 w-3 shrink-0 text-plasma" />
              <strong className="truncate">{nearestLine.species}</strong>
              <span className="truncate">{nearestLine.wavelength_air_nm.toFixed(3)} nm</span>
              {typeof (nearestLine as any).delta_nm === "number"
                ? <span className="text-slate-500">Δ {(nearestLine as any).delta_nm.toFixed(3)}</span>
                : null}
            </span>
          ) : null}
        </div>
      </div>

      <div className="relative flex-1 overflow-hidden">
        {primary == null ? (
          <EmptyPlot message="Select a spectrum from the left sidebar to view it here." />
        ) : (
          <Plot
            data={plotData}
            layout={{
              autosize: true,
              margin: { l: 60, r: 20, t: 12, b: 50 },
              paper_bgcolor: palette.paper,
              plot_bgcolor: palette.plot,
              font: { color: palette.text },
              // ``uirevision`` keyed to the spectrum + active tab keeps user
              // zoom/pan/selection state across re-renders triggered by
              // unrelated state changes (cursor, panel updates, etc).
              uirevision,
              xaxis: {
                title: "Wavelength (nm)",
                gridcolor: palette.grid,
                zeroline: false,
                // Frame to the data range on first render for each spectrum;
                // user drag-zoom takes over via uirevision until they switch
                // spectra (or hit the reset-axes toolbar button).
                ...(xAxisRange ? { range: xAxisRange } : { autorange: true }),
              },
              yaxis: { title: yAxisTitle, gridcolor: palette.grid, zeroline: false },
              legend: { orientation: "h", x: 0, y: 1.08 },
              hovermode: "closest",
              dragmode: "zoom",
              shapes:
                showWindowOverlay && clippedWindow
                  ? [
                      {
                        type: "rect",
                        xref: "x",
                        yref: "paper",
                        x0: clippedWindow[0],
                        x1: clippedWindow[1],
                        y0: 0,
                        y1: 1,
                        fillcolor: tintForTool(selectedTool),
                        line: { color: borderForTool(selectedTool), width: 1 },
                        layer: "below",
                      },
                    ]
                  : [],
            }}
            config={{
              responsive: true,
              displaylogo: false,
              // Keep autoScale2d (reset axes) and select2d (rect select for
              // setting the analysis window). Drop lasso, which we don't use.
              modeBarButtonsToRemove: ["lasso2d"],
              toImageButtonOptions: {
                format: "png",
                filename: "plasma-spec-studio",
                scale: 2,
              },
            }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
            onHover={(event: any) => {
              const point = event?.points?.[0];
              if (!point) return;
              setCursor({ x: Number(point.x), y: Number(point.y) });
            }}
            onUnhover={() => setCursor(null)}
            onSelected={(event: any) => {
              const range = event?.range?.x;
              if (Array.isArray(range) && range.length === 2) {
                const [a, b] = range;
                onSelectRegion([Math.min(a, b), Math.max(a, b)]);
              }
            }}
          />
        )}
      </div>

      {activePlotTab === "baseline" && preprocessing.length === 0 ? (
        <div className="border-t border-line bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
          Enable a preprocessing step in the Baseline tool to see the preview here.
        </div>
      ) : null}
    </div>
  );
}

function tabButtonClass(active: boolean) {
  return `inline-flex h-7 items-center px-3 text-xs font-medium transition ${
    active
      ? "border-b-2 border-plasma text-plasma"
      : "border-b-2 border-transparent text-slate-600 hover:text-slate-900"
  }`;
}

function tintForTool(tool: string) {
  if (tool === "peaks") return "rgba(0,102,255,0.08)";
  if (tool === "bands") return "rgba(67,56,202,0.07)";
  if (tool === "density") return "rgba(190,18,60,0.07)";
  if (tool === "sim") return "rgba(0,102,255,0.07)";
  if (tool === "baseline") return "rgba(180,140,30,0.07)";
  return "rgba(100,116,139,0.05)";
}

function borderForTool(tool: string) {
  if (tool === "peaks") return "rgba(0,102,255,0.38)";
  if (tool === "bands") return "rgba(67,56,202,0.35)";
  if (tool === "density") return "rgba(190,18,60,0.35)";
  if (tool === "sim") return "rgba(0,102,255,0.35)";
  if (tool === "baseline") return "rgba(180,140,30,0.35)";
  return "rgba(100,116,139,0.25)";
}

function formatY(y: number) {
  if (!Number.isFinite(y)) return "—";
  if (Math.abs(y) >= 1e4 || (Math.abs(y) < 0.001 && y !== 0)) return y.toExponential(2);
  return y.toFixed(3);
}

function EmptyPlot({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-500">
      <div>
        <FlaskConical className="mx-auto mb-2 h-10 w-10 text-slate-300" />
        <div>{message}</div>
      </div>
    </div>
  );
}
