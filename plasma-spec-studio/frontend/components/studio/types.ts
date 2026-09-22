/**
 * Shared types for the Studio workstation.
 *
 * The Studio is a single-page workspace that coordinates: which spectrum
 * (or spectra, for overlay) the user is working on, which tool the right
 * panel is showing, the current preprocessing pipeline, the selected
 * wavelength window, and the latest analysis result of any kind.
 */

import type {
  ElectronDensityResult,
  FitResult,
  PeakListResult,
  PreprocessingOperation,
  Spectrum,
  SpectrumSummary,
} from "@/lib/types";

export type StudioTool =
  | "files"
  | "qa"
  | "baseline"
  | "peaks"
  | "bands"
  | "density"
  | "sim"
  | "lines"
  | "batch";

export type StudioPlotTab = "spectrum" | "baseline" | "residuals";

export type StudioState = {
  // File selection
  spectra: SpectrumSummary[];
  selectedId?: string;
  overlayIds: Set<string>;
  loadedSpectra: Record<string, Spectrum>;
  // Workspace
  activeTool: StudioTool;
  activePlotTab: StudioPlotTab;
  preprocessing: PreprocessingOperation[];
  windowNm: [number, number];
  cursorWavelengthNm: number | null;
  // Results
  lastResult: FitResult | PeakListResult | ElectronDensityResult | null;
  lastResultKind: "peak_list" | "molecular" | "electron_density" | "fit" | null;
};
