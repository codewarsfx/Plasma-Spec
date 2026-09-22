"use client";

import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, FileText, Loader2, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { exportReport, exportUrl } from "@/lib/api";
import { toast } from "@/components/Toast";
import type {
  ElectronDensityResult,
  FitResult,
  PeakListResult,
} from "@/lib/types";

type StudioResultsTableProps = {
  result: FitResult | PeakListResult | ElectronDensityResult | null;
  kind: "peak_list" | "molecular" | "electron_density" | "fit" | null;
};

export function StudioResultsTable({ result, kind }: StudioResultsTableProps) {
  const rows = useMemo(() => normalizeResultRows(result, kind), [result, kind]);
  const columns = useMemo(() => {
    if (rows.length === 0) return [];
    return Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  }, [rows]);
  const [reportBusy, setReportBusy] = useState(false);

  async function generateReport(format: "html" | "pdf") {
    if (!result) return;
    setReportBusy(true);
    try {
      const exported = await exportReport(result as FitResult, [format]);
      const entry = exported.exports[format];
      if (entry?.export_id) {
        toast.success(`${format.toUpperCase()} report ready`, "Click the toast or use the download link.");
        window.open(exportUrl(entry.export_id), "_blank");
      }
    } catch (exc) {
      toast.error("Report failed", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setReportBusy(false);
    }
  }

  function exportCSV() {
    if (rows.length === 0) return;
    const lines = [columns.join(",")];
    for (const row of rows) {
      lines.push(
        columns
          .map((col) => formatCsvCell(row[col]))
          .join(","),
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "studio_result.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col border-t border-line bg-white">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-normal text-slate-600">
          Latest result
        </h3>
        {result ? (
          <>
            <span
              className="min-w-0 max-w-[40ch] truncate text-xs text-slate-500"
              title={`${result.filename ?? "(no filename)"} · ${
                (result as FitResult).diagnostic ?? kind ?? "result"
              }`}
            >
              {result.filename ?? "(no filename)"} · {((result as FitResult).diagnostic ?? kind ?? "result")}
            </span>
            {qualityChip((result as FitResult).fit_quality)}
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <button className="text-button" onClick={exportCSV} disabled={rows.length === 0}>
                <Download className="h-4 w-4" />
                CSV
              </button>
              <button
                className="text-button"
                onClick={() => generateReport("html")}
                disabled={reportBusy || !result}
                title="Generate a self-contained HTML report"
              >
                {reportBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                HTML
              </button>
              <button
                className="text-button"
                onClick={() => generateReport("pdf")}
                disabled={reportBusy || !result}
                title="Generate a one-page PDF report"
              >
                {reportBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                PDF
              </button>
            </div>
          </>
        ) : (
          <span className="text-xs text-slate-500">No analysis run yet</span>
        )}
      </div>
      <div className="flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs text-slate-500">
            <div>
              <FileSpreadsheet className="mx-auto mb-2 h-8 w-8 text-slate-300" />
              Results appear here after you run a peak-list, band fit, or electron-density analysis.
            </div>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="border-b border-line px-2 py-1.5 text-[11px] uppercase tracking-normal text-slate-600"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="odd:bg-white even:bg-slate-50">
                  {columns.map((col) => (
                    <td key={col} className="border-b border-line px-2 py-1.5 tabular-nums">
                      {formatCell(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function qualityChip(quality?: string) {
  if (quality === "good") {
    return (
      <span className="inline-flex items-center gap-1 border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-900" style={{ borderRadius: 999 }}>
        <CheckCircle2 className="h-3 w-3" />good
      </span>
    );
  }
  if (quality === "bad") {
    return (
      <span className="inline-flex items-center gap-1 border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-900" style={{ borderRadius: 999 }}>
        <XCircle className="h-3 w-3" />bad
      </span>
    );
  }
  if (quality === "warning") {
    return (
      <span className="inline-flex items-center gap-1 border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-950" style={{ borderRadius: 999 }}>
        <AlertTriangle className="h-3 w-3" />warn
      </span>
    );
  }
  return null;
}

function normalizeResultRows(
  result: FitResult | PeakListResult | ElectronDensityResult | null,
  kind: "peak_list" | "molecular" | "electron_density" | "fit" | null,
): Array<Record<string, unknown>> {
  if (!result) return [];
  if (kind === "peak_list" && Array.isArray((result as PeakListResult).results)) {
    return (result as PeakListResult).results.map((entry) => {
      const data = entry.data ?? {};
      const fit = (entry.fit ?? {}) as Record<string, unknown>;
      return {
        label: entry.label,
        species: entry.species ?? "",
        quality: entry.fit_quality,
        center_nm: (data as Record<string, number>).peak_wavelength_nm ?? null,
        height_corr: (data as Record<string, number>).peak_height_baseline_subtracted ?? null,
        area: (data as Record<string, number>).baseline_subtracted_area ?? null,
        fwhm_data: (data as Record<string, number>).fwhm_data_nm ?? null,
        snr: (data as Record<string, number>).snr ?? null,
        fit_center: fit.center_nm ?? null,
        fit_fwhm: fit.fwhm_nm ?? null,
        fit_r2: fit.r2 ?? null,
        warnings: entry.warnings.join("; "),
      };
    });
  }
  if (kind === "electron_density") {
    const erd = result as ElectronDensityResult;
    const ed: Record<string, any> = (erd.electron_density ?? {}) as Record<string, any>;
    const bd: Record<string, any> = (erd.fwhm_breakdown_nm ?? {}) as Record<string, any>;
    const ci: Record<string, any> = (ed.confidence_interval_95 ?? {}) as Record<string, any>;
    const params: Record<string, any> = ((erd as unknown as Record<string, any>).parameters ?? {}) as Record<string, any>;
    const metrics: Record<string, any> = ((erd as unknown as Record<string, any>).metrics ?? {}) as Record<string, any>;
    return [
      {
        n_e_cm3: ed.electron_density_cm3 ?? null,
        ne_lower_95: ci.lower_cm3 ?? null,
        ne_upper_95: ci.upper_cm3 ?? null,
        stark_fwhm_nm: bd.stark_fwhm_nm ?? null,
        lorentz_fwhm_nm: bd.lorentz_fwhm_nm ?? bd.lorentz1_fwhm_nm ?? null,
        vdw_fwhm_nm: bd.vdw_fwhm_nm ?? null,
        inst_gauss_fwhm_nm: bd.instrument_gauss_fwhm_nm ?? null,
        Tg_K: params.Tg_K ?? null,
        line: erd.line ?? null,
        model: erd.model ?? null,
        R2: metrics.r2 ?? null,
      },
    ];
  }
  // Default: flatten parameters + metrics
  const r = result as FitResult;
  const flat: Record<string, unknown> = {
    diagnostic: r.diagnostic,
    quality: r.fit_quality,
  };
  for (const [k, v] of Object.entries(r.parameters ?? {})) flat[k] = v;
  for (const [k, v] of Object.entries(r.metrics ?? {})) flat[`metric_${k}`] = v;
  return [flat];
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Math.abs(value) >= 1e5 || (Math.abs(value) < 0.001 && value !== 0)) {
      return value.toExponential(3);
    }
    return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  return String(value);
}

function formatCsvCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") {
    const escaped = value.replace(/"/g, '""');
    return /[",\n]/.test(value) ? `"${escaped}"` : escaped;
  }
  return String(value);
}
