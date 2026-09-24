"use client";

import {
  Activity,
  Atom,
  Beaker,
  Database,
  Download,
  FileSpreadsheet,
  FlaskConical,
  Gauge,
  ListChecks,
  Sliders,
  Zap,
} from "lucide-react";
import type { StudioTool } from "./types";

type StudioToolbarProps = {
  activeTool: StudioTool;
  onSelectTool: (tool: StudioTool) => void;
  spectrumLoaded: boolean;
  onExport?: () => void;
};

const TOOLS: Array<{
  id: StudioTool;
  label: string;
  description: string;
  icon: typeof FlaskConical;
}> = [
  {
    id: "files",
    label: "Files",
    description: "Inspect a spectrum, overlay multiple, manage metadata",
    icon: FlaskConical,
  },
  {
    id: "qa",
    label: "QA",
    description: "Spectrum readiness checks for saturation, SNR, spacing, and coverage",
    icon: Gauge,
  },
  {
    id: "baseline",
    label: "Baseline",
    description: "Preprocessing pipeline (crop, baseline, smooth, despike)",
    icon: Sliders,
  },
  {
    id: "peaks",
    label: "Peaks",
    description: "Wavelength-list peak areas + Voigt fits, search atomic lines",
    icon: ListChecks,
  },
  {
    id: "bands",
    label: "Bands",
    description: "Molecular fit (OH, N2, NH, NO, N2+) for Trot / Tvib",
    icon: Beaker,
  },
  {
    id: "density",
    label: "Density",
    description: "Electron density from H-alpha Stark broadening (lab Gigosos)",
    icon: Zap,
  },
  {
    id: "sim",
    label: "Sim",
    description: "NIST-backed atomic forward model for T_exc, species scales, shift, and instrument width",
    icon: Atom,
  },
  {
    id: "lines",
    label: "Lines",
    description: "Browse the bundled NIST atomic line catalog",
    icon: Database,
  },
  {
    id: "batch",
    label: "Batch",
    description: "Run a recipe across many spectra, export long-form table",
    icon: Activity,
  },
];

export function StudioToolbar({ activeTool, onSelectTool, spectrumLoaded, onExport }: StudioToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-1">
        {TOOLS.map((tool) => {
          const Icon = tool.icon;
          const active = activeTool === tool.id;
          return (
            <button
              key={tool.id}
              className={`inline-flex h-9 items-center gap-2 border px-3 text-sm font-medium transition focus-ring ${
                active
                  ? "border-plasma bg-teal-50 text-teal-900"
                  : "border-transparent text-slate-700 hover:bg-slate-100"
              }`}
              style={{ borderRadius: 6 }}
              onClick={() => onSelectTool(tool.id)}
              title={tool.description}
              aria-pressed={active}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{tool.label}</span>
            </button>
          );
        })}
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-2">
        {!spectrumLoaded && activeTool !== "lines" ? (
          <span className="hidden truncate text-xs text-slate-500 md:inline">
            Select a spectrum on the left to start
          </span>
        ) : null}
        {onExport ? (
          <button
            className="text-button"
            onClick={onExport}
            disabled={!spectrumLoaded}
            title="Export latest result + figure"
          >
            <Download className="h-4 w-4" />
            Export
          </button>
        ) : null}
      </div>
    </div>
  );
}
