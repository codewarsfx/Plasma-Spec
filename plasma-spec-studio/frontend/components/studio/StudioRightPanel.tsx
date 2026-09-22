"use client";

import { CheckCircle2, FlaskConical, Layers } from "lucide-react";
import { useRef } from "react";
import { AtomicForwardModelPanel } from "@/components/AtomicForwardModelPanel";
import { AtomicLineSearchPanel } from "@/components/AtomicLineSearchPanel";
import { DiagnosticId, DiagnosticSelector } from "@/components/DiagnosticSelector";
import { ElectronDensityPanel } from "@/components/ElectronDensityPanel";
import { FittingPanel } from "@/components/FittingPanel";
import { PreprocessingPanel } from "@/components/PreprocessingPanel";
import { SpectralQAPanel } from "@/components/SpectralQAPanel";
import {
  WavelengthListPanel,
  type WavelengthListPanelHandle,
} from "@/components/WavelengthListPanel";
import type { FitResult, PeakListResult, PreprocessingOperation, Spectrum } from "@/lib/types";
import type { StudioTool } from "./types";

type StudioRightPanelProps = {
  tool: StudioTool;
  spectrumId?: string;
  /** The full selected spectrum once it has loaded - used for the Files panel summary. */
  selectedSpectrum?: Spectrum | null;
  /** Catalog of all spectra, so the Files panel can announce how many are uploaded. */
  spectraCount?: number;
  windowNm: [number, number];
  onWindowChange: (range: [number, number]) => void;
  preprocessing: PreprocessingOperation[];
  onPreprocessingChange: (operations: PreprocessingOperation[]) => void;
  diagnostic: DiagnosticId;
  onChangeDiagnostic: (next: DiagnosticId, window: [number, number]) => void;
  onResult: (result: FitResult | PeakListResult) => void;
};

/**
 * The right panel just stacks the tool-specific panel components vertically.
 * Each child panel renders its OWN ``<section className="panel p-4">`` with
 * its own header - the router does NOT wrap them in an extra section, because
 * that produced double-nested cards with duplicate titles and 2x padding.
 *
 * For tools that don't have a dedicated panel component (Files, Batch), we
 * render a single bare info card in matching panel style.
 */
export function StudioRightPanel(props: StudioRightPanelProps) {
  const wavelengthListRef = useRef<WavelengthListPanelHandle | null>(null);
  const tool = props.tool;

  return (
    <div className="flex h-full flex-col gap-3">
      {tool === "files" ? (
        <FilesOnboardingPanel
          spectraCount={props.spectraCount ?? 0}
          selectedSpectrum={props.selectedSpectrum ?? null}
        />
      ) : null}

      {tool === "qa" ? (
        <SpectralQAPanel spectrum={props.selectedSpectrum ?? null} />
      ) : null}

      {tool === "baseline" ? (
        <PreprocessingPanel
          operations={props.preprocessing}
          onChange={props.onPreprocessingChange}
          windowNm={props.windowNm}
          onWindowChange={props.onWindowChange}
        />
      ) : null}

      {tool === "peaks" ? (
        <>
          <WavelengthListPanel
            ref={wavelengthListRef}
            spectrumId={props.spectrumId}
            preprocessing={props.preprocessing}
            onResult={props.onResult}
          />
          <AtomicLineSearchPanel
            onAddPeak={(peak) => wavelengthListRef.current?.addPeak(peak)}
          />
        </>
      ) : null}

      {tool === "bands" ? (
        <>
          <DiagnosticSelector
            diagnostic={props.diagnostic}
            onChange={props.onChangeDiagnostic}
          />
          <FittingPanel
            spectrumId={props.spectrumId}
            diagnostic={props.diagnostic}
            windowNm={props.windowNm}
            preprocessing={props.preprocessing}
            onResult={props.onResult}
          />
        </>
      ) : null}

      {tool === "density" ? (
        <ElectronDensityPanel
          spectrumId={props.spectrumId}
          preprocessing={props.preprocessing}
          onResult={props.onResult}
          windowNm={props.windowNm}
          onWindowChange={props.onWindowChange}
        />
      ) : null}

      {tool === "sim" ? (
        <AtomicForwardModelPanel
          spectrumId={props.spectrumId}
          preprocessing={props.preprocessing}
          windowNm={props.windowNm}
          onWindowChange={props.onWindowChange}
          onResult={props.onResult}
        />
      ) : null}

      {tool === "lines" ? <AtomicLineSearchPanel /> : null}

      {tool === "batch" ? (
        <InfoCard
          icon={<Layers className="h-4 w-4 text-plasma" />}
          title="Batch"
          body={
            <>
              Batch runs use saved recipes. Open the{" "}
              <a className="font-medium text-teal-800 underline" href="/batch">
                Batch page
              </a>{" "}
              to pick a recipe and run it across many spectra. Saved recipes live on the{" "}
              <a className="font-medium text-teal-800 underline" href="/recipes">
                Recipes page
              </a>
              .
            </>
          }
        />
      ) : null}
    </div>
  );
}

function InfoCard({
  title,
  icon,
  body,
}: {
  title: string;
  icon?: React.ReactNode;
  body: React.ReactNode;
}) {
  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
      </div>
      <p className="text-xs leading-relaxed text-slate-600">{body}</p>
    </section>
  );
}

/**
 * Adaptive onboarding panel for the Files tool:
 *  - Always shows the 4-step Studio workflow with a check next to completed steps.
 *  - When a spectrum is selected, shows its metadata + range so the user can
 *    confirm they picked the right file and decide which tool to use next.
 */
function FilesOnboardingPanel({
  spectraCount,
  selectedSpectrum,
}: {
  spectraCount: number;
  selectedSpectrum: Spectrum | null;
}) {
  const hasFiles = spectraCount > 0;
  const hasSelection = selectedSpectrum != null;

  return (
    <>
      <section className="panel p-4">
        <div className="mb-3 flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-plasma" />
          <h2 className="text-sm font-semibold text-ink">Get started</h2>
        </div>
        <ol className="grid gap-2 text-xs text-slate-600">
          <Step
            done={hasFiles}
            n={1}
            title="Upload spectra"
            body="Use the ↑ icon in the left sidebar (CSV, TXT, TSV, ASC, DAT, XLSX, XLSM all work)."
          />
          <Step
            done={hasSelection}
            n={2}
            title="Click a file in the sidebar"
            body="The row highlights blue and the plot draws the spectrum. Click the eye icon to add a second file as an overlay."
          />
          <Step
            done={false}
            n={3}
            title="Pick a tool in the top bar"
            body={
              <>
                <strong>Peaks</strong> for line areas + Voigt fits, <strong>Bands</strong> for
                Trot / Tvib, <strong>Density</strong> for n_e (Stark), <strong>Baseline</strong>{" "}
                for preprocessing.
              </>
            }
          />
          <Step
            done={false}
            n={4}
            title="Configure → Run → Export"
            body="The right panel changes with the tool. Results show in the bottom strip; CSV / HTML / PDF buttons are there too."
          />
        </ol>
      </section>

      {hasSelection ? (
        <section className="panel p-4">
          <div className="mb-2 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-teal-700" />
            <h2 className="text-sm font-semibold text-ink">Selected spectrum</h2>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-slate-500">File</dt>
            <dd className="truncate font-medium text-ink" title={selectedSpectrum.filename}>
              {selectedSpectrum.filename}
            </dd>
            <dt className="text-slate-500">Range</dt>
            <dd className="tabular-nums text-ink">
              {selectedSpectrum.wavelength_nm.length > 0
                ? `${selectedSpectrum.wavelength_nm[0].toFixed(1)} – ${selectedSpectrum.wavelength_nm[selectedSpectrum.wavelength_nm.length - 1].toFixed(1)} nm`
                : "—"}
            </dd>
            <dt className="text-slate-500">Points</dt>
            <dd className="tabular-nums text-ink">
              {selectedSpectrum.wavelength_nm.length.toLocaleString()}
            </dd>
            {Object.entries(selectedSpectrum.metadata ?? {})
              .filter(([, v]) => v != null && String(v).length > 0)
              .slice(0, 12)
              .map(([key, value]) => (
                <FilesMetaRow key={key} keyLabel={key} value={value} />
              ))}
          </dl>
          <p className="mt-3 border-t border-line pt-3 text-xs text-slate-600">
            <strong>Suggested next:</strong>{" "}
            {suggestNextTool(selectedSpectrum)}
          </p>
        </section>
      ) : (
        <section className="panel p-4">
          <p className="text-xs leading-relaxed text-slate-600">
            {hasFiles
              ? "You have files uploaded but none selected yet. Click any row in the left sidebar."
              : "No spectra uploaded yet. Drop files into the sidebar's upload control."}
          </p>
        </section>
      )}
    </>
  );
}

function Step({
  n,
  done,
  title,
  body,
}: {
  n: number;
  done: boolean;
  title: string;
  body: React.ReactNode;
}) {
  return (
    <li className="grid grid-cols-[auto_1fr] gap-2">
      <div
        className={`mt-0.5 flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
          done
            ? "bg-teal-100 text-teal-800"
            : "bg-slate-100 text-slate-500"
        }`}
      >
        {done ? <CheckCircle2 className="h-3 w-3" /> : n}
      </div>
      <div>
        <div className={`text-xs font-semibold ${done ? "text-teal-900" : "text-ink"}`}>
          {title}
        </div>
        <div className="text-[11px] leading-relaxed text-slate-600">{body}</div>
      </div>
    </li>
  );
}

function FilesMetaRow({
  keyLabel,
  value,
}: {
  keyLabel: string;
  value: unknown;
}) {
  const display = typeof value === "number" ? value.toString() : String(value);
  return (
    <>
      <dt className="truncate text-slate-500" title={keyLabel}>
        {keyLabel}
      </dt>
      <dd className="truncate text-ink" title={display}>
        {display}
      </dd>
    </>
  );
}

function suggestNextTool(spectrum: Spectrum): string {
  const xs = spectrum.wavelength_nm;
  if (!xs || xs.length === 0) return "Pick a tool from the top bar.";
  const lo = xs[0];
  const hi = xs[xs.length - 1];

  const tips: string[] = [];
  if (lo <= 312 && hi >= 306) tips.push("Bands → OH(A-X) at 306–312 nm");
  if (lo <= 339 && hi >= 334) tips.push("Bands → N₂(C-B) at 334–339 nm");
  if (lo <= 658 && hi >= 654) tips.push("Density → H-α Stark at 656 nm");
  if (lo <= 488 && hi >= 484) tips.push("Bands → H-β at 484–488 nm");
  if (lo <= 845 && hi >= 695) tips.push("Peaks → Ar I line series 696–842 nm");

  if (tips.length === 0) return "Try Peaks or Baseline on the loaded range.";
  return tips.join(" · ");
}
