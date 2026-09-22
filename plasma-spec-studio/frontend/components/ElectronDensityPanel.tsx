"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  XCircle,
  Zap,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { computeElectronDensity } from "@/lib/api";
import type { ElectronDensityResult, PreprocessingOperation } from "@/lib/types";
import { useThemePalette } from "@/lib/useThemePalette";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as any;

type Props = {
  spectrumId?: string;
  preprocessing: PreprocessingOperation[];
  onResult?: (result: ElectronDensityResult) => void;
  /** Optional parent-controlled window. When provided, the panel writes its
   *  window min/max back to the parent so the Studio plot's tinted highlight
   *  follows the Density window. */
  windowNm?: [number, number];
  onWindowChange?: (range: [number, number]) => void;
};

export function ElectronDensityPanel({
  spectrumId,
  preprocessing,
  onResult,
  windowNm,
  onWindowChange,
}: Props) {
  const palette = useThemePalette();
  const [TgK, setTgK] = useState(650);
  const [instrumentGaussFwhmNm, setInstrumentGaussFwhmNm] = useState(0.13);
  const [model, setModel] = useState<"single_voigt" | "two_voigt">("single_voigt");
  const [line, setLine] = useState<"halpha" | "hbeta">("halpha");
  const [windowMin, setWindowMin] = useState<string>(
    windowNm ? String(windowNm[0]) : "",
  );
  const [windowMax, setWindowMax] = useState<string>(
    windowNm ? String(windowNm[1]) : "",
  );
  const [thresholdRel, setThresholdRel] = useState(0.05);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ElectronDensityResult | null>(null);

  // Sync from parent: when the user drag-selects on the plot, the parent
  // updates windowNm and we mirror those values into the inputs.
  useEffect(() => {
    if (!windowNm) return;
    setWindowMin(String(windowNm[0]));
    setWindowMax(String(windowNm[1]));
  }, [windowNm]);

  // Sync to parent: when the user types valid window values, push them up
  // so the plot's tinted highlight follows.
  function pushWindowUp(min: string, max: string) {
    if (!onWindowChange) return;
    const lo = Number(min);
    const hi = Number(max);
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo < hi) {
      onWindowChange([lo, hi]);
    }
  }

  // Clear stale results when the spectrum changes so the headline n_e / chip
  // / width breakdown don't show numbers from the previous spectrum's fit.
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [spectrumId]);

  async function runFit() {
    if (!spectrumId) return;
    setBusy(true);
    setError(null);
    try {
      const win =
        windowMin && windowMax
          ? ([Number(windowMin), Number(windowMax)] as [number, number])
          : null;
      const response = await computeElectronDensity({
        spectrum_id: spectrumId,
        Tg_K: Number(TgK),
        instrument_gauss_fwhm_nm: Number(instrumentGaussFwhmNm),
        line,
        model,
        window_nm: win,
        intensity_threshold_rel: Number(thresholdRel),
        preprocessing,
      });
      setResult(response);
      onResult?.(response);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Electron density fit failed");
    } finally {
      setBusy(false);
    }
  }

  const plotData = useMemo(() => {
    if (!result?.measured_curve?.length || !result?.fit_curve?.length) return [];
    return [
      {
        type: "scatter",
        mode: "markers",
        x: result.measured_curve.map((p) => p.wavelength_nm),
        y: result.measured_curve.map((p) => p.value),
        name: "Data (normalized)",
        marker: { color: "#0066ff", size: 5, opacity: 0.6 },
      },
      {
        type: "scatter",
        mode: "lines",
        x: result.fit_curve.map((p) => p.wavelength_nm),
        y: result.fit_curve.map((p) => p.value),
        name: "Voigt fit",
        line: { color: "#4338ca", width: 2 },
      },
    ];
  }, [result]);

  const residuals = useMemo(() => {
    if (!result?.residual_curve?.length) return [];
    return [
      {
        type: "scatter",
        mode: "lines",
        x: result.residual_curve.map((p) => p.wavelength_nm),
        y: result.residual_curve.map((p) => p.value),
        name: "Residuals",
        line: { color: "#be123c", width: 1 },
      },
    ];
  }, [result]);

  const ed = result?.electron_density;
  const bd = result?.fwhm_breakdown_nm;

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-plasma" />
        <h2 className="text-sm font-semibold text-ink">Electron Density (Stark / Gigosos)</h2>
        <span className="ml-auto text-xs text-slate-500">H-α primary; H-β cross-check</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label
          className="grid gap-1"
          title="Gas temperature in K. Used for the van der Waals broadening correction Δλ_vdW = 5.12 / Tg^0.7. Lab default = 650 K (set from your OH or N2 Trot fit when available)."
        >
          <span className="control-label flex items-center">
            Tg (K)
            <span className="hint-pill">?</span>
          </span>
          <input
            className="field"
            type="number"
            step="10"
            value={TgK}
            onChange={(event) => setTgK(Number(event.target.value))}
          />
        </label>
        <label
          className="grid gap-1"
          title="Combined instrumental + Doppler Gaussian FWHM, held fixed during the Voigt fit. Lab default = 0.13 nm (measured from narrow Ar lines on the same spectrometer)."
        >
          <span className="control-label flex items-center">
            Inst Gauss FWHM (nm)
            <span className="hint-pill">?</span>
          </span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={instrumentGaussFwhmNm}
            onChange={(event) => setInstrumentGaussFwhmNm(Number(event.target.value))}
          />
        </label>
        <label
          className="grid gap-1"
          title="Drop points below this fraction of the peak intensity before normalizing. Matches MATLAB ElectronDensity.m default (0.05 = 5%)."
        >
          <span className="control-label flex items-center">
            Threshold (frac)
            <span className="hint-pill">?</span>
          </span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={thresholdRel}
            onChange={(event) => setThresholdRel(Number(event.target.value))}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Model</span>
          <select
            className="field"
            value={model}
            onChange={(event) => setModel(event.target.value as "single_voigt" | "two_voigt")}
          >
            <option value="single_voigt">Single Voigt</option>
            <option value="two_voigt">Two Voigt</option>
          </select>
        </label>
        <label className="col-span-2 grid gap-1">
          <span className="control-label">Line</span>
          <select
            className="field"
            value={line}
            onChange={(event) => setLine(event.target.value as "halpha" | "hbeta")}
          >
            <option value="halpha">H-α 656.279 nm (lab Gigosos C=1.78)</option>
            <option value="hbeta">H-β 486.135 nm (Gigosos C=4.84; not lab-validated)</option>
          </select>
        </label>
        <label className="grid gap-1">
          <span className="control-label">Window min (nm)</span>
          <input
            className="field"
            type="number"
            step="1"
            placeholder="default"
            value={windowMin}
            onChange={(event) => {
              setWindowMin(event.target.value);
              pushWindowUp(event.target.value, windowMax);
            }}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Window max (nm)</span>
          <input
            className="field"
            type="number"
            step="1"
            placeholder="default"
            value={windowMax}
            onChange={(event) => {
              setWindowMax(event.target.value);
              pushWindowUp(windowMin, event.target.value);
            }}
          />
        </label>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button className="primary-button" onClick={runFit} disabled={!spectrumId || busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Compute n_e
        </button>
        {!spectrumId ? (
          <span className="text-xs text-slate-500">Select a spectrum on the left first.</span>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="mt-4 grid gap-4">
          {/* Headline result */}
          <div className="border border-line bg-slate-50 p-3" style={{ borderRadius: 8 }}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-normal text-slate-600">
                Electron density
              </h3>
              {qualityChip(result.fit_quality)}
            </div>
            <div className="text-3xl font-semibold text-ink tabular-nums">
              {ed?.electron_density_cm3 != null
                ? `${ed.electron_density_cm3.toExponential(3)}`
                : "n/a"}
              <span className="ml-2 text-base font-normal text-slate-500">cm⁻³</span>
            </div>
            {ed?.confidence_interval_95?.lower_cm3 != null
            && ed?.confidence_interval_95?.upper_cm3 != null ? (
              <div className="mt-1 text-xs text-slate-600">
                95% CI from wL fit:{" "}
                <span className="tabular-nums">
                  {ed.confidence_interval_95.lower_cm3.toExponential(2)} –{" "}
                  {ed.confidence_interval_95.upper_cm3.toExponential(2)} cm⁻³
                </span>
              </div>
            ) : null}
            {ed?.warning ? (
              <div className="mt-2 flex gap-2 border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950" style={{ borderRadius: 6 }}>
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{ed.warning}</span>
              </div>
            ) : null}
          </div>

          {/* Intermediate-value breakdown */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
              Width breakdown (every value traceable)
            </h3>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              <ValueCard label="Instrument Gauss FWHM (nm)" value={bd?.instrument_gauss_fwhm_nm} />
              <ValueCard label="Fitted Lorentz FWHM (nm)" value={bd?.lorentz_fwhm_nm ?? bd?.lorentz1_fwhm_nm} />
              {bd?.lorentz2_fwhm_nm != null ? (
                <ValueCard label="Lorentz FWHM pop2 (nm)" value={bd.lorentz2_fwhm_nm} />
              ) : null}
              <ValueCard label="van der Waals FWHM (nm)" value={bd?.vdw_fwhm_nm} />
              <ValueCard label="Stark FWHM (nm)" value={bd?.stark_fwhm_nm} highlight />
              <ValueCard label="Voigt total FWHM (nm)" value={bd?.voigt_total_fwhm_nm} />
            </div>
          </div>

          {/* Calibration provenance */}
          <div className="border border-line bg-white p-3 text-xs text-slate-600" style={{ borderRadius: 6 }}>
            <div className="font-semibold text-ink">Calibration source</div>
            <div className="mt-1">{result.calibration_source ?? "(not reported)"}</div>
            <div className="mt-1 text-slate-500">
              Stark constant C = {result.stark_constant_nm ?? "?"} nm. vdW =
              {" "}
              {result.vdw_prefactor_nm ?? 0} / Tg^{result.vdw_tg_exponent ?? 0}
              {" "}nm. Tg used: {result.Tg_K} K.
            </div>
            {result.calibration_validated === false ? (
              <div className="mt-2 flex gap-2 border border-amber-200 bg-amber-50 px-2 py-1.5 text-amber-950" style={{ borderRadius: 4 }}>
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Calibration is a literature cross-check, not validated against the lab.</span>
              </div>
            ) : null}
          </div>

          {/* Voigt overlay plot */}
          {plotData.length > 0 ? (
            <div className="border border-line overflow-hidden" style={{ borderRadius: 6 }}>
              <Plot
                data={plotData}
                layout={{
                  height: 320,
                  margin: { l: 60, r: 20, t: 30, b: 50 },
                  paper_bgcolor: palette.paper,
                  plot_bgcolor: palette.plot,
                  font: { color: palette.text },
                  xaxis: { title: "Wavelength (nm)", gridcolor: palette.grid },
                  yaxis: { title: "Normalized intensity", gridcolor: palette.grid },
                  legend: { orientation: "h", x: 0, y: 1.12 },
                  hovermode: "x unified",
                }}
                config={{ responsive: true, displaylogo: false }}
                style={{ width: "100%", height: 320 }}
                useResizeHandler
              />
            </div>
          ) : null}

          {/* Residuals */}
          {residuals.length > 0 ? (
            <div className="border border-line overflow-hidden" style={{ borderRadius: 6 }}>
              <Plot
                data={residuals}
                layout={{
                  height: 180,
                  margin: { l: 60, r: 20, t: 20, b: 40 },
                  paper_bgcolor: palette.paper,
                  plot_bgcolor: palette.plot,
                  font: { color: palette.text },
                  xaxis: { title: "Wavelength (nm)", gridcolor: palette.grid },
                  yaxis: { title: "Residual", gridcolor: palette.grid, zeroline: true, zerolinecolor: palette.muted },
                  showlegend: false,
                  hovermode: "x unified",
                }}
                config={{ responsive: true, displaylogo: false }}
                style={{ width: "100%", height: 180 }}
                useResizeHandler
              />
            </div>
          ) : null}

          {result.warnings?.length ? (
            <div className="grid gap-2">
              {result.warnings.map((warning, index) => (
                <div
                  key={`${warning}-${index}`}
                  className="flex gap-2 border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
                  style={{ borderRadius: 6 }}
                >
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{warning}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function qualityChip(quality: string | undefined) {
  if (quality === "good") {
    return (
      <span className="inline-flex items-center gap-1 border border-teal-200 bg-teal-50 px-2 py-0.5 text-xs font-semibold text-teal-900" style={{ borderRadius: 999 }}>
        <CheckCircle2 className="h-3.5 w-3.5" />good
      </span>
    );
  }
  if (quality === "bad") {
    return (
      <span className="inline-flex items-center gap-1 border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-900" style={{ borderRadius: 999 }}>
        <XCircle className="h-3.5 w-3.5" />bad
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-950" style={{ borderRadius: 999 }}>
      <AlertTriangle className="h-3.5 w-3.5" />warning
    </span>
  );
}

function ValueCard({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number | null | undefined;
  highlight?: boolean;
}) {
  return (
    <div
      className={`border px-3 py-2 ${highlight ? "border-teal-200 bg-teal-50" : "border-line bg-slate-50"}`}
      style={{ borderRadius: 6 }}
    >
      <div className="text-[11px] uppercase tracking-normal text-slate-600">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${highlight ? "text-teal-900" : "text-ink"}`}>
        {formatValue(value)}
      </div>
    </div>
  );
}

function formatValue(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1e4 || (Math.abs(value) < 0.001 && value !== 0)) {
    return value.toExponential(3);
  }
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}
