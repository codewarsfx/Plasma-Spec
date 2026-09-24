"use client";

import { useEffect, useMemo, useState } from "react";
import {
  computeElectronDensity,
  getSpectrum,
  preprocessSpectrum,
} from "@/lib/api";
import { toast } from "@/components/Toast";
import type {
  ElectronDensityResult,
  FitResult,
  PeakListResult,
  PreprocessingOperation,
  Spectrum,
  SpectrumSummary,
} from "@/lib/types";
import { DiagnosticId } from "@/components/DiagnosticSelector";
import { StudioCenterPlot } from "./StudioCenterPlot";
import { StudioResultsTable } from "./StudioResultsTable";
import { StudioRightPanel } from "./StudioRightPanel";
import { StudioSidebar } from "./StudioSidebar";
import { StudioToolbar } from "./StudioToolbar";
import type { StudioPlotTab, StudioTool } from "./types";

/**
 * Top-level workstation. Coordinates state across sidebar, plot, right panel,
 * and bottom results table:
 *
 * - Selecting a file on the left loads it into the central plot.
 * - The toolbar drives which contextual panel appears on the right.
 * - Preprocessing changes in the Baseline panel show up as a "processed"
 *   overlay in the Baseline preview tab.
 * - Running any analysis (peak list, molecular fit, electron density) updates
 *   the bottom results table immediately.
 */
export function StudioShell() {
  const [spectra, setSpectra] = useState<SpectrumSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [overlayIds, setOverlayIds] = useState<Set<string>>(new Set());
  const [loadedSpectra, setLoadedSpectra] = useState<Record<string, Spectrum>>({});
  const [activeTool, setActiveTool] = useState<StudioTool>("files");
  const [activePlotTab, setActivePlotTab] = useState<StudioPlotTab>("spectrum");
  const [preprocessing, setPreprocessing] = useState<PreprocessingOperation[]>([]);
  // Default window is intentionally a wide visible range, not the OH 306-312
  // band - if the spectrum doesn't contain that range the highlight rect would
  // distort the plot's auto-frame. The plot itself clips the highlight to the
  // data range, so a too-wide default is safe.
  const [windowNm, setWindowNm] = useState<[number, number]>([300, 900]);
  const [diagnostic, setDiagnostic] = useState<DiagnosticId>("oh_ax");
  const [preprocessed, setPreprocessed] = useState<Spectrum | null>(null);
  const [lastResult, setLastResult] = useState<
    FitResult | PeakListResult | ElectronDensityResult | null
  >(null);
  const [lastResultKind, setLastResultKind] = useState<
    "peak_list" | "molecular" | "electron_density" | "fit" | null
  >(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Load the primary spectrum when selected
  useEffect(() => {
    if (!selectedId) return;
    if (loadedSpectra[selectedId]) return;
    let cancelled = false;
    getSpectrum(selectedId)
      .then((spec) => {
        if (!cancelled) {
          setLoadedSpectra((current) => ({ ...current, [selectedId]: spec }));
        }
      })
      .catch((exc) => {
        if (!cancelled) {
          setStatusMessage(
            exc instanceof Error ? exc.message : "Failed to load spectrum",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, loadedSpectra]);

  // Load any overlays as they get toggled on
  useEffect(() => {
    const missing = Array.from(overlayIds).filter((id) => !loadedSpectra[id]);
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(missing.map((id) => getSpectrum(id).then((spec) => [id, spec] as const)))
      .then((pairs) => {
        if (cancelled) return;
        setLoadedSpectra((current) => {
          const next = { ...current };
          for (const [id, spec] of pairs) next[id] = spec;
          return next;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [overlayIds, loadedSpectra]);

  // Recompute preprocessed view whenever preprocessing or selection changes
  useEffect(() => {
    if (!selectedId || preprocessing.length === 0) {
      setPreprocessed(null);
      return;
    }
    let cancelled = false;
    preprocessSpectrum(selectedId, preprocessing, false)
      .then((response) => {
        if (!cancelled) setPreprocessed(response.spectrum);
      })
      .catch((exc) => {
        if (!cancelled) {
          setStatusMessage(
            exc instanceof Error ? exc.message : "Preprocessing preview failed",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, preprocessing]);

  const primarySpectrum = selectedId ? loadedSpectra[selectedId] ?? null : null;
  const overlaySpectra = useMemo(() => {
    return Array.from(overlayIds)
      .filter((id) => id !== selectedId && loadedSpectra[id])
      .map((id) => loadedSpectra[id]);
  }, [overlayIds, loadedSpectra, selectedId]);

  // Snap the wavelength window to the active tool's canonical range so the
  // tinted plot highlight makes sense without the user having to type.
  // We only do this when the user hasn't drag-selected a custom range yet
  // for the current tool, signalled by the window being one of our presets.
  function snapWindowForTool(tool: StudioTool) {
    setActiveTool(tool);
    setWindowNm((current) => {
      const presets: [number, number][] = [
        [300, 900],
        [306, 312],
        [334, 339],
        [600, 700],
        [630, 680],
        [484, 488],
        [388, 392],
        [335, 338],
        [357, 425],
      ];
      const isPreset = presets.some(([lo, hi]) => lo === current[0] && hi === current[1]);
      if (!isPreset) return current; // user has a custom selection - don't clobber it
      if (tool === "density") return [600, 700];
      if (tool === "sim") return [300, 900];
      if (tool === "bands") {
        if (diagnostic === "n2_cb") return [334, 339];
        if (diagnostic === "n2plus_bx") return [388, 392];
        if (diagnostic === "nh_ax") return [335, 338];
        if (diagnostic === "no_bx") return [357, 425];
        if (diagnostic === "hbeta_voigt") return [484, 488];
        return [306, 312];
      }
      if (tool === "peaks") return [300, 900];
      return current;
    });
  }

  function handleSelectSpectrum(id: string) {
    setSelectedId(id);
    // Clear stale results when the active spectrum changes
    setLastResult(null);
    setLastResultKind(null);
  }

  function handleToggleOverlay(id: string) {
    setOverlayIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleSpectrumDeleted(id: string) {
    setLoadedSpectra((current) => {
      if (!(id in current)) return current;
      const next = { ...current };
      delete next[id];
      return next;
    });
    setOverlayIds((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
    if (selectedId === id) {
      setSelectedId(undefined);
      setLastResult(null);
      setLastResultKind(null);
    }
  }

  function handleSelectRegion(range: [number, number]) {
    setWindowNm(range);
  }

  function handleChangeDiagnostic(next: DiagnosticId, window: [number, number]) {
    setDiagnostic(next);
    setWindowNm(window);
    setLastResult(null);
  }

  function handleFitResult(result: FitResult | PeakListResult | ElectronDensityResult) {
    setLastResult(result);
    const diagnosticName = (result as FitResult).diagnostic;
    const kind: "peak_list" | "molecular" | "electron_density" | "fit" =
      diagnosticName === "peak_list" || Array.isArray((result as PeakListResult).results)
        ? "peak_list"
        : diagnosticName === "electron_density"
          ? "electron_density"
          : diagnosticName?.startsWith("molecular")
            || diagnosticName === "oh_ax"
            || diagnosticName === "n2_cb"
            ? "molecular"
            : "fit";
    setLastResultKind(kind);
    setActivePlotTab("spectrum");
    const quality = resultQuality(result);
    if (quality === "bad") {
      toast.warning(
        `${kind === "peak_list" ? "Peak list" : kind === "molecular" ? "Molecular fit" : kind === "electron_density" ? "Density fit" : "Fit"} returned low quality`,
        firstWarning(result),
      );
    } else {
      toast.success(
        `${kind === "peak_list" ? "Peak list" : kind === "molecular" ? "Molecular fit" : kind === "electron_density" ? "Density fit" : "Fit"} complete`,
      );
    }
  }

  return (
    <div className="studio-shell">
      <div className="studio-toolbar-area">
        <StudioToolbar
          activeTool={activeTool}
          onSelectTool={snapWindowForTool}
          spectrumLoaded={primarySpectrum != null}
        />
      </div>

      <div className="studio-sidebar-area min-h-0 overflow-hidden">
        <StudioSidebar
          spectra={spectra}
          onSpectraChange={setSpectra}
          selectedId={selectedId}
          overlayIds={overlayIds}
          onSelectSpectrum={handleSelectSpectrum}
          onToggleOverlay={handleToggleOverlay}
          onSpectrumDeleted={handleSpectrumDeleted}
        />
      </div>

      <div className="studio-plot-area min-h-0 min-w-0 overflow-auto">
        <StudioCenterPlot
          primary={primarySpectrum}
          overlays={overlaySpectra}
          preprocessed={preprocessed}
          fitResult={isFitLike(lastResult) ? (lastResult as FitResult) : null}
          activePlotTab={activePlotTab}
          onChangePlotTab={setActivePlotTab}
          windowNm={windowNm}
          onSelectRegion={handleSelectRegion}
          preprocessing={preprocessing}
          selectedTool={activeTool}
        />
      </div>

      <div className="studio-results-area min-h-0 min-w-0 overflow-auto">
        <StudioResultsTable result={lastResult} kind={lastResultKind} />
      </div>

      <div
        key={activeTool}
        className="studio-right-area tool-pane min-h-0 overflow-auto border-l border-line bg-slate-50 p-3"
      >
        <StudioRightPanel
          tool={activeTool}
          spectrumId={selectedId}
          selectedSpectrum={primarySpectrum}
          spectraCount={spectra.length}
          windowNm={windowNm}
          onWindowChange={setWindowNm}
          preprocessing={preprocessing}
          onPreprocessingChange={setPreprocessing}
          diagnostic={diagnostic}
          onChangeDiagnostic={handleChangeDiagnostic}
          onResult={handleFitResult}
        />
      </div>

      {statusMessage ? (
        <div
          className="fixed bottom-4 right-4 max-w-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 shadow-md"
          style={{ borderRadius: 6 }}
        >
          {statusMessage}
          <button
            className="ml-3 text-xs underline"
            onClick={() => setStatusMessage(null)}
          >
            dismiss
          </button>
        </div>
      ) : null}
    </div>
  );
}

function isFitLike(
  result: FitResult | PeakListResult | ElectronDensityResult | null,
): boolean {
  if (!result) return false;
  const r = result as FitResult;
  return (
    Array.isArray(r.measured_curve)
    || Array.isArray(r.fit_curve)
    || Array.isArray(r.residual_curve)
  );
}

function resultQuality(result: FitResult | PeakListResult | ElectronDensityResult) {
  const fitQuality = (result as FitResult).fit_quality;
  if (fitQuality) return fitQuality;
  const peakRows = (result as PeakListResult).results;
  if (Array.isArray(peakRows) && peakRows.some((row) => row.fit_quality === "bad")) return "bad";
  if (Array.isArray(peakRows) && peakRows.some((row) => row.fit_quality === "warning")) return "warning";
  return "good";
}

function firstWarning(result: FitResult | PeakListResult | ElectronDensityResult) {
  const warnings = (result as FitResult).warnings;
  if (warnings?.length) return warnings[0];
  const peakRows = (result as PeakListResult).results;
  if (Array.isArray(peakRows)) {
    return peakRows.find((row) => row.warnings.length > 0)?.warnings[0];
  }
  return undefined;
}
