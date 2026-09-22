"use client";

import { Atom, Loader2, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fitAtomicForward } from "@/lib/api";
import type {
  AtomicLineContribution,
  FitResult,
  PreprocessingOperation,
} from "@/lib/types";
import { toast } from "@/components/Toast";

type Props = {
  spectrumId?: string;
  preprocessing: PreprocessingOperation[];
  windowNm: [number, number];
  onWindowChange: (range: [number, number]) => void;
  onResult: (result: FitResult) => void;
};

type InstrumentProfile = "gaussian" | "voigt";

export function AtomicForwardModelPanel({
  spectrumId,
  preprocessing,
  windowNm,
  onWindowChange,
  onResult,
}: Props) {
  const [speciesText, setSpeciesText] = useState("H I, Ar I, O I, N II");
  const [windowMin, setWindowMin] = useState(String(windowNm[0]));
  const [windowMax, setWindowMax] = useState(String(windowNm[1]));
  const [initialTemperature, setInitialTemperature] = useState(9000);
  const [fitTemperature, setFitTemperature] = useState(true);
  const [instrumentProfile, setInstrumentProfile] = useState<InstrumentProfile>("gaussian");
  const [instrumentFwhm, setInstrumentFwhm] = useState(0.15);
  const [fitInstrumentFwhm, setFitInstrumentFwhm] = useState(true);
  const [instrumentLorentzFwhm, setInstrumentLorentzFwhm] = useState(0.05);
  const [fitInstrumentLorentz, setFitInstrumentLorentz] = useState(false);
  const [wavelengthShift, setWavelengthShift] = useState(0);
  const [fitWavelengthShift, setFitWavelengthShift] = useState(true);
  const [fitSpeciesScales, setFitSpeciesScales] = useState(true);
  const [baselineOrder, setBaselineOrder] = useState<0 | 1>(1);
  const [maxLines, setMaxLines] = useState(3000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FitResult | null>(null);

  useEffect(() => {
    setWindowMin(String(windowNm[0]));
    setWindowMax(String(windowNm[1]));
  }, [windowNm]);

  const species = useMemo(
    () =>
      speciesText
        .split(/[,;\n]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    [speciesText],
  );

  function pushWindow(min: string, max: string) {
    const lo = Number(min);
    const hi = Number(max);
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo < hi) {
      onWindowChange([lo, hi]);
    }
  }

  async function runFit() {
    if (!spectrumId || species.length === 0) return;
    const lo = Number(windowMin);
    const hi = Number(windowMax);
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) {
      setError("Window must be ordered low < high.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const response = await fitAtomicForward({
        spectrum_id: spectrumId,
        species,
        window_nm: [lo, hi],
        preprocessing,
        initial_temperature_K: Number(initialTemperature),
        temperature_bounds_K: [1000, 30000],
        fit_temperature: fitTemperature,
        instrument_profile: instrumentProfile,
        instrument_fwhm_nm: Number(instrumentFwhm),
        instrument_fwhm_bounds_nm: [0.02, 2],
        fit_instrument_fwhm: fitInstrumentFwhm,
        instrument_lorentz_fwhm_nm: instrumentProfile === "voigt" ? Number(instrumentLorentzFwhm) : 0,
        instrument_lorentz_fwhm_bounds_nm: [0, 2],
        fit_instrument_lorentz: instrumentProfile === "voigt" && fitInstrumentLorentz,
        wavelength_shift_nm: Number(wavelengthShift),
        wavelength_shift_bounds_nm: [-1, 1],
        fit_wavelength_shift: fitWavelengthShift,
        fit_species_scales: fitSpeciesScales,
        baseline_order: baselineOrder,
        max_lines: Number(maxLines),
        top_contributions: 50,
      });
      setResult(response);
      onResult(response);
      toast.success("Atomic forward fit complete", qualityLine(response));
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Atomic forward fit failed";
      setError(message);
      toast.error("Atomic forward fit failed", message);
    } finally {
      setBusy(false);
    }
  }

  const params = (result?.parameters ?? {}) as Record<string, any>;
  const contributions = ((result as any)?.line_contributions ?? []) as AtomicLineContribution[];
  const speciesScales = (params.species_scales ?? {}) as Record<string, number>;

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center gap-2">
        <Atom className="h-4 w-4 text-plasma" />
        <h2 className="text-sm font-semibold text-ink">Atomic Forward Model</h2>
        <span className="ml-auto text-xs text-slate-500">
          {result ? qualityLine(result) : `${windowMin}-${windowMax} nm`}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 grid gap-1">
          <span className="control-label">Species</span>
          <input
            className="field"
            value={speciesText}
            onChange={(event) => setSpeciesText(event.target.value)}
          />
        </label>

        <label className="grid gap-1">
          <span className="control-label">Min nm</span>
          <input
            className="field"
            type="number"
            step="1"
            value={windowMin}
            onChange={(event) => {
              setWindowMin(event.target.value);
              pushWindow(event.target.value, windowMax);
            }}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Max nm</span>
          <input
            className="field"
            type="number"
            step="1"
            value={windowMax}
            onChange={(event) => {
              setWindowMax(event.target.value);
              pushWindow(windowMin, event.target.value);
            }}
          />
        </label>

        <label className="grid gap-1">
          <span className="control-label">Initial T_exc K</span>
          <input
            className="field"
            type="number"
            step="250"
            value={initialTemperature}
            onChange={(event) => setInitialTemperature(Number(event.target.value))}
          />
        </label>
        <label className="flex items-center gap-2 pt-6 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-blue-700"
            checked={fitTemperature}
            onChange={(event) => setFitTemperature(event.target.checked)}
          />
          Fit T_exc
        </label>

        <label className="grid gap-1">
          <span className="control-label">Profile</span>
          <select
            className="field"
            value={instrumentProfile}
            onChange={(event) => setInstrumentProfile(event.target.value as InstrumentProfile)}
          >
            <option value="gaussian">Gaussian</option>
            <option value="voigt">Voigt</option>
          </select>
        </label>
        <label className="grid gap-1">
          <span className="control-label">Gauss FWHM nm</span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={instrumentFwhm}
            onChange={(event) => setInstrumentFwhm(Number(event.target.value))}
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-blue-700"
            checked={fitInstrumentFwhm}
            onChange={(event) => setFitInstrumentFwhm(event.target.checked)}
          />
          Fit Gauss width
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-blue-700"
            checked={fitWavelengthShift}
            onChange={(event) => setFitWavelengthShift(event.target.checked)}
          />
          Fit wavelength shift
        </label>

        <label className="grid gap-1">
          <span className="control-label">Shift nm</span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={wavelengthShift}
            onChange={(event) => setWavelengthShift(Number(event.target.value))}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Max lines</span>
          <input
            className="field"
            type="number"
            min={1}
            max={50000}
            value={maxLines}
            onChange={(event) => setMaxLines(Number(event.target.value))}
          />
        </label>

        {instrumentProfile === "voigt" ? (
          <>
            <label className="grid gap-1">
              <span className="control-label">Lorentz FWHM nm</span>
              <input
                className="field"
                type="number"
                step="0.01"
                value={instrumentLorentzFwhm}
                onChange={(event) => setInstrumentLorentzFwhm(Number(event.target.value))}
              />
            </label>
            <label className="flex items-center gap-2 pt-6 text-xs text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 accent-blue-700"
                checked={fitInstrumentLorentz}
                onChange={(event) => setFitInstrumentLorentz(event.target.checked)}
              />
              Fit Lorentz width
            </label>
          </>
        ) : null}

        <label className="flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-blue-700"
            checked={fitSpeciesScales}
            onChange={(event) => setFitSpeciesScales(event.target.checked)}
          />
          Fit species scales
        </label>
        <label className="grid gap-1">
          <span className="control-label">Baseline</span>
          <select
            className="field"
            value={baselineOrder}
            onChange={(event) => setBaselineOrder(Number(event.target.value) as 0 | 1)}
          >
            <option value={0}>Constant</option>
            <option value={1}>Linear</option>
          </select>
        </label>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          className="primary-button"
          onClick={runFit}
          disabled={!spectrumId || species.length === 0 || busy}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Fit atomic model
        </button>
        {!spectrumId ? <span className="text-xs text-slate-500">Select a spectrum</span> : null}
      </div>

      {error ? (
        <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="mt-3 grid gap-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Metric label="T_exc" value={formatNumber(params.temperature_K, " K")} />
            <Metric label="R²" value={formatNumber(result.metrics?.r2)} />
            <Metric label="Gauss FWHM" value={formatNumber(params.instrument_fwhm_nm, " nm")} />
            <Metric label="Shift" value={formatSigned(params.wavelength_shift_nm, " nm")} />
            <Metric label="Lines used" value={String(params.line_count_used ?? "—")} />
            <Metric label="Excluded" value={String(params.excluded_missing_physics ?? "—")} />
          </div>

          {Object.keys(speciesScales).length > 0 ? (
            <div className="border border-line bg-white p-2 text-xs" style={{ borderRadius: 6 }}>
              <div className="mb-1 font-semibold text-ink">Species scales</div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                {Object.entries(speciesScales).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <span className="text-slate-600">{key}</span>
                    <span className="tabular-nums text-ink">{formatNumber(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {result.warnings?.length ? (
            <div className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950" style={{ borderRadius: 6 }}>
              {result.warnings.slice(0, 3).join(" ")}
            </div>
          ) : null}

          {contributions.length > 0 ? (
            <div className="max-h-72 overflow-auto border border-line" style={{ borderRadius: 6 }}>
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-[11px] uppercase tracking-normal text-slate-600">
                  <tr>
                    <th className="border-b border-line px-2 py-1.5">Species</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">λ nm</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">Rel</th>
                    <th className="border-b border-line px-2 py-1.5">Transition</th>
                  </tr>
                </thead>
                <tbody>
                  {contributions.slice(0, 30).map((line, index) => (
                    <tr key={`${line.species}-${line.wavelength_air_nm}-${index}`} className="odd:bg-white even:bg-slate-50">
                      <td className="border-b border-line px-2 py-1.5 font-medium text-ink">{line.species}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                        {line.wavelength_air_nm.toFixed(3)}
                      </td>
                      <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                        {line.relative_strength.toFixed(3)}
                      </td>
                      <td className="border-b border-line px-2 py-1.5 text-slate-700">
                        {line.transition ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line bg-white px-2 py-1.5" style={{ borderRadius: 6 }}>
      <div className="text-[11px] uppercase text-slate-500">{label}</div>
      <div className="truncate font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function qualityLine(result: FitResult) {
  const r2 = result.metrics?.r2;
  return typeof r2 === "number" ? `R² ${r2.toFixed(3)} · ${result.fit_quality}` : result.fit_quality;
}

function formatNumber(value: unknown, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (Math.abs(number) >= 1e5 || (Math.abs(number) < 0.001 && number !== 0)) {
    return `${number.toExponential(2)}${suffix}`;
  }
  return `${number.toLocaleString(undefined, { maximumFractionDigits: 3 })}${suffix}`;
}

function formatSigned(value: unknown, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(3)}${suffix}`;
}
