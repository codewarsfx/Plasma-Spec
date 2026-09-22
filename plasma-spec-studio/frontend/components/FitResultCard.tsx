"use client";

import { AlertTriangle, CheckCircle2, Database, XCircle } from "lucide-react";
import type { FitResult } from "@/lib/types";

type FitResultCardProps = {
  result?: FitResult | null;
};

export function FitResultCard({ result }: FitResultCardProps) {
  if (!result) {
    return (
      <section className="panel p-4">
        <h2 className="text-sm font-semibold text-ink">Fit Result</h2>
        <p className="mt-3 text-sm text-slate-500">No result yet</p>
      </section>
    );
  }

  const quality = qualityStyle(result.fit_quality);
  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Fit Result</h2>
        <span className={`inline-flex items-center gap-1 border px-2 py-1 text-xs font-semibold ${quality.className}`} style={{ borderRadius: 999 }}>
          <quality.Icon className="h-3.5 w-3.5" />
          {result.fit_quality ?? "analysis"}
        </span>
      </div>

      <div className="grid gap-3">
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

        {result.analysis_notes?.length ? (
          <div className="grid gap-2">
            {result.analysis_notes.map((note, index) => (
              <div
                key={`${note}-${index}`}
                className="border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950"
                style={{ borderRadius: 6 }}
              >
                {note}
              </div>
            ))}
          </div>
        ) : null}

        {result.database_kind === "demo" || result.warnings?.some((warning) => warning.includes("Demo database")) ? (
          <div className="flex gap-2 border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950" style={{ borderRadius: 6 }}>
            <Database className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Demo molecular data are marked in exports.</span>
          </div>
        ) : null}

        <KeyValueGrid
          title="Parameters"
          values={result.parameters ?? {}}
          stderrs={(result.parameter_stderr ?? {}) as Record<string, unknown>}
        />
        <KeyValueGrid title="Metrics" values={result.metrics ?? {}} />

        {result.instrument_widths_nm ? (
          <KeyValueGrid title="Instrument widths (nm)" values={result.instrument_widths_nm as Record<string, unknown>} />
        ) : null}

        {Array.isArray((result as { restart_log?: unknown }).restart_log)
          && ((result as { restart_log?: unknown[] }).restart_log?.length ?? 0) > 1 ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
              Multi-restart log
            </h3>
            <div className="border border-line bg-slate-50 px-2 py-1.5 text-xs text-slate-700" style={{ borderRadius: 6 }}>
              {((result as { restart_log: Array<Record<string, unknown>> }).restart_log).map((entry, index) => (
                <div key={index} className="flex justify-between gap-3">
                  <span>init Trot {String(entry.initial_trot_K)} K</span>
                  <span className="tabular-nums">
                    cost {entry.cost != null ? formatValue(entry.cost) : "error"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {result.boltzmann_by_v?.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
              Apparent Boltzmann Slopes
            </h3>
            <div className="max-h-44 overflow-auto border border-line" style={{ borderRadius: 6 }}>
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="border-b border-line px-2 py-1.5">v&apos;</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">Trot K</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">R²</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">States</th>
                  </tr>
                </thead>
                <tbody>
                  {result.boltzmann_by_v.map((row, index) => (
                    <tr key={index}>
                      <td className="border-b border-line px-2 py-1.5">{formatValue(row.v_upper)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.apparent_trot_K)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.r2)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.state_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {result.state_populations?.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
              State Populations
            </h3>
            <div className="max-h-64 overflow-auto border border-line" style={{ borderRadius: 6 }}>
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="border-b border-line px-2 py-1.5">v&apos;</th>
                    <th className="border-b border-line px-2 py-1.5">J&apos;</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">Rel pop</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">E rot</th>
                    <th className="border-b border-line px-2 py-1.5 text-right">Lines</th>
                  </tr>
                </thead>
                <tbody>
                  {result.state_populations.slice(0, 80).map((row, index) => (
                    <tr key={`${String(row.state_key)}-${index}`}>
                      <td className="border-b border-line px-2 py-1.5">{formatValue(row.v_upper)}</td>
                      <td className="border-b border-line px-2 py-1.5">{formatValue(row.j_upper)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.relative_population)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.e_rot_upper_cm1)}</td>
                      <td className="border-b border-line px-2 py-1.5 text-right">{formatValue(row.line_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {result.detected_peaks?.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">Possible Lines</h3>
            <div className="max-h-52 overflow-auto border border-line" style={{ borderRadius: 6 }}>
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="border-b border-line px-2 py-1.5">Detected nm</th>
                    <th className="border-b border-line px-2 py-1.5">Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {result.detected_peaks.map((peak, index) => (
                    <tr key={index}>
                      <td className="border-b border-line px-2 py-1.5">
                        {formatValue(peak.detected_wavelength_nm)}
                      </td>
                      <td className="border-b border-line px-2 py-1.5">
                        {formatAssignments(peak.possible_assignments)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function KeyValueGrid({
  title,
  values,
  stderrs,
}: {
  title: string;
  values: Record<string, unknown>;
  stderrs?: Record<string, unknown>;
}) {
  const entries = Object.entries(values).filter(([, value]) => value !== undefined);
  if (entries.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">{title}</h3>
      <div className="grid grid-cols-2 gap-2">
        {entries.map(([key, value]) => {
          const stderr = stderrs?.[key];
          const stderrText =
            typeof stderr === "number" && Number.isFinite(stderr)
              ? `± ${formatValue(stderr)}`
              : null;
          return (
            <div key={key} className="border border-line bg-slate-50 px-2 py-1.5" style={{ borderRadius: 6 }}>
              <div className="truncate text-[11px] uppercase tracking-normal text-slate-500">{key}</div>
              <div className="truncate text-sm font-semibold text-ink">{formatValue(value)}</div>
              {stderrText ? (
                <div className="truncate text-[10px] text-slate-500">{stderrText}</div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function qualityStyle(quality: string) {
  if (quality === "good") {
    return { Icon: CheckCircle2, className: "border-teal-200 bg-teal-50 text-teal-900" };
  }
  if (quality === "bad") {
    return { Icon: XCircle, className: "border-red-200 bg-red-50 text-red-900" };
  }
  return { Icon: AlertTriangle, className: "border-amber-200 bg-amber-50 text-amber-950" };
}

function formatValue(value: unknown) {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.01) return value.toExponential(3);
    return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (value == null) return "null";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function formatAssignments(assignments: unknown) {
  if (!Array.isArray(assignments) || assignments.length === 0) return "";
  return assignments
    .map((item) => {
      if (typeof item !== "object" || item === null) return "";
      const entry = item as Record<string, unknown>;
      return `${entry.species ?? ""} ${entry.transition ?? ""}`;
    })
    .filter(Boolean)
    .join("; ");
}
