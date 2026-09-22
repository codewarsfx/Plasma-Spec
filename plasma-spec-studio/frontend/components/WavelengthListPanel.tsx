"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ListChecks,
  Loader2,
  Play,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import { useImperativeHandle, useMemo, useState, forwardRef } from "react";
import { analyzePeakList } from "@/lib/api";
import type {
  PeakListEntry,
  PeakListResult,
  PeakListSingleResult,
  PreprocessingOperation,
} from "@/lib/types";

export type WavelengthListPanelHandle = {
  addPeak: (peak: PeakListEntry) => void;
};

type WavelengthListPanelProps = {
  spectrumId?: string;
  preprocessing: PreprocessingOperation[];
  defaultHalfWidthNm?: number;
  onResult?: (result: PeakListResult) => void;
};

type PeakRow = PeakListEntry & {
  // local-only id used for stable React keys; not sent to the backend
  _row: string;
};

const FIT_MODELS: Array<"gaussian" | "lorentzian" | "voigt" | ""> = [
  "",
  "gaussian",
  "lorentzian",
  "voigt",
];

const INITIAL_PEAKS: PeakRow[] = [
  { _row: "halpha", label: "H-alpha", center_nm: 656.279, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
  { _row: "hbeta", label: "H-beta", center_nm: 486.135, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
];

const PLASMA_MARKER_PRESETS: Array<{
  id: string;
  label: string;
  peaks: PeakListEntry[];
}> = [
  {
    id: "water_air",
    label: "Water/air markers",
    peaks: [
      { label: "OH 309", center_nm: 309.0, half_width_nm: 2.0, fit_model: null, species: "OH" },
      { label: "N2 337", center_nm: 337.13, half_width_nm: 1.5, fit_model: null, species: "N2" },
      { label: "NH 336", center_nm: 336.0, half_width_nm: 1.2, fit_model: null, species: "NH" },
      { label: "N2+ 391", center_nm: 391.44, half_width_nm: 1.2, fit_model: null, species: "N2+" },
      { label: "H-beta", center_nm: 486.135, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
      { label: "H-alpha", center_nm: 656.279, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
      { label: "O I 777", center_nm: 777.194, half_width_nm: 1.0, fit_model: "voigt", species: "O I" },
      { label: "O I 844", center_nm: 844.636, half_width_nm: 1.0, fit_model: "voigt", species: "O I" },
    ],
  },
  {
    id: "argon",
    label: "Argon markers",
    peaks: [
      { label: "Ar I 696", center_nm: 696.543, half_width_nm: 0.8, fit_model: "voigt", species: "Ar I" },
      { label: "Ar I 706", center_nm: 706.722, half_width_nm: 0.8, fit_model: "voigt", species: "Ar I" },
      { label: "Ar I 750", center_nm: 750.387, half_width_nm: 0.8, fit_model: "voigt", species: "Ar I" },
      { label: "Ar I 763", center_nm: 763.511, half_width_nm: 0.8, fit_model: "voigt", species: "Ar I" },
      { label: "Ar I 811", center_nm: 811.531, half_width_nm: 0.8, fit_model: "voigt", species: "Ar I" },
      { label: "O I 777", center_nm: 777.194, half_width_nm: 1.0, fit_model: "voigt", species: "O I" },
      { label: "O I 844", center_nm: 844.636, half_width_nm: 1.0, fit_model: "voigt", species: "O I" },
    ],
  },
];

function rowId() {
  return Math.random().toString(36).slice(2, 9);
}

export const WavelengthListPanel = forwardRef<WavelengthListPanelHandle, WavelengthListPanelProps>(
  function WavelengthListPanel(
    { spectrumId, preprocessing, defaultHalfWidthNm = 0.5, onResult },
    ref,
  ) {
    const [peaks, setPeaks] = useState<PeakRow[]>(INITIAL_PEAKS);
    const [result, setResult] = useState<PeakListResult | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useImperativeHandle(ref, () => ({
      addPeak(peak) {
        setPeaks((current) => [
          ...current,
          { _row: rowId(), half_width_nm: defaultHalfWidthNm, ...peak },
        ]);
      },
    }));

    function updatePeak(rowKey: string, patch: Partial<PeakRow>) {
      setPeaks((current) =>
        current.map((row) => (row._row === rowKey ? { ...row, ...patch } : row)),
      );
    }

    function removePeak(rowKey: string) {
      setPeaks((current) => current.filter((row) => row._row !== rowKey));
    }

    function addBlankPeak() {
      setPeaks((current) => [
        ...current,
        { _row: rowId(), label: "", center_nm: 0, half_width_nm: defaultHalfWidthNm, fit_model: null },
      ]);
    }

    function addPresetPeaks(peaksToAdd: PeakListEntry[]) {
      setPeaks((current) => {
        const next = [...current];
        for (const peak of peaksToAdd) {
          const duplicate = next.some(
            (row) => Math.abs(Number(row.center_nm) - Number(peak.center_nm)) < 0.02,
          );
          if (!duplicate) {
            next.push({ _row: rowId(), half_width_nm: defaultHalfWidthNm, ...peak });
          }
        }
        return next;
      });
    }

    async function runAnalysis() {
      if (!spectrumId) return;
      const cleaned: PeakListEntry[] = peaks
        .filter((row) => Number.isFinite(row.center_nm) && row.center_nm > 0)
        .map(({ _row, fit_model, ...rest }) => ({
          ...rest,
          fit_model: fit_model || null,
        }));
      if (cleaned.length === 0) {
        setError("Enter at least one peak with a valid center wavelength");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const response = await analyzePeakList({
          spectrum_id: spectrumId,
          peaks: cleaned,
          preprocessing,
          default_half_width_nm: defaultHalfWidthNm,
        });
        setResult(response);
        onResult?.(response);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Peak list analysis failed");
      } finally {
        setBusy(false);
      }
    }

    const csvHref = useMemo(() => {
      if (!result?.results?.length) return null;
      const rows = result.results.map((row) => flattenPeakRow(row, result.filename));
      const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
      const csv = [
        headers.join(","),
        ...rows.map((row) =>
          headers
            .map((header) => formatCsvCell(row[header]))
            .join(","),
        ),
      ].join("\n");
      return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    }, [result]);

    const ratioRows = useMemo(
      () => result?.results ? computeDiagnosticRatios(result.results) : [],
      [result],
    );

    return (
      <section className="panel p-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-plasma" />
            <h2 className="text-sm font-semibold text-ink">Wavelength List Analysis</h2>
          </div>
          <span className="text-xs text-slate-500">
            {peaks.length} peak{peaks.length === 1 ? "" : "s"}
          </span>
        </div>

        <p className="mb-3 text-xs leading-relaxed text-slate-600">
          One row per wavelength. Run, get area / height / FWHM / SNR for each. Add a fit model
          for fitted center + FWHM + R².
        </p>

        <div className="mb-3 flex flex-wrap gap-2">
          {PLASMA_MARKER_PRESETS.map((preset) => (
            <button
              key={preset.id}
              className="text-button"
              onClick={() => addPresetPeaks(preset.peaks)}
              title={`Add ${preset.peaks.length} common low-temperature plasma marker lines`}
            >
              <Plus className="h-4 w-4" />
              {preset.label}
            </button>
          ))}
        </div>

        <div className="grid gap-2">
          {peaks.map((peak, index) => (
            <div
              key={peak._row}
              className="rounded border border-line bg-white p-2"
            >
              <div className="mb-1.5 flex items-center gap-2">
                <span className="w-5 shrink-0 text-[10px] font-semibold text-slate-400">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <input
                  className="field h-7 min-w-0 flex-1 px-2 text-xs"
                  placeholder="Label (e.g. H-alpha)"
                  value={peak.label ?? ""}
                  onChange={(event) => updatePeak(peak._row, { label: event.target.value })}
                />
                <button
                  className="icon-button h-7 w-7 shrink-0"
                  onClick={() => removePeak(peak._row)}
                  title="Remove peak"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-[1fr_1fr_1.2fr_1fr] gap-2">
                <label className="grid gap-0.5">
                  <span className="text-[10px] uppercase tracking-normal text-slate-500">
                    Center nm
                  </span>
                  <input
                    className="field h-7 w-full px-2 text-xs tabular-nums"
                    type="number"
                    step="0.001"
                    value={peak.center_nm}
                    onChange={(event) =>
                      updatePeak(peak._row, { center_nm: Number(event.target.value) })
                    }
                  />
                </label>
                <label className="grid gap-0.5">
                  <span className="text-[10px] uppercase tracking-normal text-slate-500">
                    ± nm
                  </span>
                  <input
                    className="field h-7 w-full px-2 text-xs tabular-nums"
                    type="number"
                    step="0.05"
                    value={peak.half_width_nm ?? defaultHalfWidthNm}
                    onChange={(event) =>
                      updatePeak(peak._row, { half_width_nm: Number(event.target.value) })
                    }
                  />
                </label>
                <label className="grid gap-0.5">
                  <span className="text-[10px] uppercase tracking-normal text-slate-500">
                    Fit
                  </span>
                  <select
                    className="field h-7 w-full px-1 text-xs"
                    value={peak.fit_model ?? ""}
                    onChange={(event) =>
                      updatePeak(peak._row, {
                        fit_model: (event.target.value || null) as PeakRow["fit_model"],
                      })
                    }
                  >
                    {FIT_MODELS.map((model) => (
                      <option key={model || "none"} value={model}>
                        {model || "none"}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-0.5">
                  <span className="text-[10px] uppercase tracking-normal text-slate-500">
                    Species
                  </span>
                  <input
                    className="field h-7 w-full px-2 text-xs"
                    placeholder="Ar I"
                    value={peak.species ?? ""}
                    onChange={(event) =>
                      updatePeak(peak._row, { species: event.target.value })
                    }
                  />
                </label>
              </div>
            </div>
          ))}
          {peaks.length === 0 ? (
            <div className="rounded border border-dashed border-line px-3 py-6 text-center text-xs text-slate-500">
              No peaks yet. Click <strong>Add row</strong> or use the Line Database to add lines.
            </div>
          ) : null}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="text-button" onClick={addBlankPeak}>
            <Plus className="h-4 w-4" />
            Add row
          </button>
          <button className="primary-button" onClick={runAnalysis} disabled={busy || !spectrumId}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run
          </button>
          {csvHref ? (
            <a className="text-button" href={csvHref} download="peak_list_results.csv">
              <Download className="h-4 w-4" />
              CSV
            </a>
          ) : null}
          {!spectrumId ? (
            <span className="text-xs text-slate-500">Select a spectrum on the left first.</span>
          ) : null}
        </div>

        {error ? (
          <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
            {error}
          </div>
        ) : null}

        {result?.results?.length ? (
          <>
            {ratioRows.length ? (
              <div className="mt-3 border border-line bg-slate-50 px-3 py-2" style={{ borderRadius: 6 }}>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
                  Diagnostic Ratios
                </h3>
                <div className="grid gap-1 text-xs">
                  {ratioRows.map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-3">
                      <span className="truncate text-slate-700">{row.label}</span>
                      <span className="font-semibold tabular-nums text-ink">{formatNumber(row.value, 4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-3 overflow-hidden border border-line" style={{ borderRadius: 6 }}>
              <div className="max-h-72 overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-white text-[11px] uppercase tracking-normal text-slate-600">
                    <tr>
                      <th className="border-b border-line px-2 py-1.5">Label</th>
                      <th className="border-b border-line px-2 py-1.5">Q</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">Data center nm</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">Height (corr)</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">Area (corr)</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">FWHM data</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">Fit center nm</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">FWHM fit</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">R²</th>
                      <th className="border-b border-line px-2 py-1.5 text-right">SNR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.map((row, index) => (
                      <tr key={index} className="odd:bg-white even:bg-slate-50">
                        <td className="border-b border-line px-2 py-1.5">
                          <div className="font-medium text-ink">{row.label}</div>
                          {row.warnings?.length ? (
                            <div className="mt-1 text-[10px] text-amber-900">{row.warnings.join("; ")}</div>
                          ) : null}
                        </td>
                        <td className="border-b border-line px-2 py-1.5">{qualityBadge(row.fit_quality)}</td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.data?.peak_wavelength_nm, 3)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.data?.peak_height_baseline_subtracted, 2)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.data?.baseline_subtracted_area, 3)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.data?.fwhm_data_nm, 4)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.fit?.center_nm as number | undefined, 4)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.fit?.fwhm_nm as number | undefined, 4)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.fit?.r2 as number | undefined, 4)}
                        </td>
                        <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                          {formatNumber(row.data?.snr, 1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </section>
    );
  },
);

function qualityBadge(quality: string) {
  if (quality === "good") {
    return (
      <span className="inline-flex items-center gap-1 text-teal-800">
        <CheckCircle2 className="h-3.5 w-3.5" />
        good
      </span>
    );
  }
  if (quality === "bad") {
    return (
      <span className="inline-flex items-center gap-1 text-red-800">
        <XCircle className="h-3.5 w-3.5" />
        bad
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-amber-800">
      <AlertTriangle className="h-3.5 w-3.5" />
      warn
    </span>
  );
}

function formatNumber(value: number | null | undefined, digits: number) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  if (Math.abs(value) >= 1e5 || (Math.abs(value) < 0.001 && value !== 0)) {
    return value.toExponential(2);
  }
  return value.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "");
}

function formatCsvCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") {
    const escaped = value.replace(/"/g, '""');
    return /[",\n]/.test(value) ? `"${escaped}"` : escaped;
  }
  return String(value);
}

function flattenPeakRow(row: PeakListSingleResult, filename?: string) {
  const fit = row.fit ?? {};
  const data = row.data ?? {};
  return {
    filename,
    label: row.label,
    species: row.species ?? "",
    requested_center_nm: row.requested_center_nm,
    fit_quality: row.fit_quality,
    fit_model: row.fit_model ?? "",
    window_min_nm: row.window_nm[0],
    window_max_nm: row.window_nm[1],
    data_center_nm: (data as Record<string, number>).peak_wavelength_nm ?? null,
    data_height_baseline_subtracted: (data as Record<string, number>).peak_height_baseline_subtracted ?? null,
    integrated_area: (data as Record<string, number>).integrated_area ?? null,
    baseline_subtracted_area: (data as Record<string, number>).baseline_subtracted_area ?? null,
    fwhm_data_nm: (data as Record<string, number>).fwhm_data_nm ?? null,
    snr: (data as Record<string, number>).snr ?? null,
    fit_center_nm: (fit as Record<string, number>).center_nm ?? null,
    fit_fwhm_nm: (fit as Record<string, number>).fwhm_nm ?? null,
    fit_area: (fit as Record<string, number>).fit_area ?? null,
    fit_r2: (fit as Record<string, number>).r2 ?? null,
    fit_rmse: (fit as Record<string, number>).rmse ?? null,
    warnings: row.warnings.join("; "),
  } as Record<string, unknown>;
}

function computeDiagnosticRatios(rows: PeakListSingleResult[]) {
  const byLabel = new Map(rows.map((row) => [normalizeLabel(row.label), row]));
  const ratioSpecs = [
    { label: "H-alpha / H-beta", numerator: "h-alpha", denominator: "h-beta" },
    { label: "N2+ 391 / N2 337", numerator: "n2+ 391", denominator: "n2 337" },
    { label: "OH 309 / N2 337", numerator: "oh 309", denominator: "n2 337" },
    { label: "O I 777 / O I 844", numerator: "o i 777", denominator: "o i 844" },
    { label: "Ar I 750 / Ar I 811", numerator: "ar i 750", denominator: "ar i 811" },
  ];
  return ratioSpecs
    .map((spec) => {
      const numerator = rowArea(byLabel.get(spec.numerator));
      const denominator = rowArea(byLabel.get(spec.denominator));
      if (numerator == null || denominator == null || denominator <= 0) return null;
      return { label: spec.label, value: numerator / denominator };
    })
    .filter((row): row is { label: string; value: number } => row !== null);
}

function rowArea(row?: PeakListSingleResult) {
  const value = row?.data?.baseline_subtracted_area;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeLabel(label: string) {
  return label.toLowerCase().replace(/\s+/g, " ").trim();
}
