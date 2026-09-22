"use client";

import { AlertTriangle, CheckCircle2, Gauge, XCircle } from "lucide-react";
import { useMemo } from "react";
import type { Spectrum } from "@/lib/types";

type SpectralQAPanelProps = {
  spectrum?: Spectrum | null;
};

type QAStatus = "good" | "warning" | "bad";

type QACheck = {
  label: string;
  value: string;
  status: QAStatus;
};

const COVERAGE_WINDOWS: Array<{ label: string; range: [number, number] }> = [
  { label: "OH(A-X) 306-312", range: [306, 312] },
  { label: "N2(C-B) 334-339", range: [334, 339] },
  { label: "NH/N2 335-338", range: [335, 338] },
  { label: "N2+(B-X) 388-392", range: [388, 392] },
  { label: "H-beta 484-488", range: [484, 488] },
  { label: "H-alpha 654-659", range: [654, 659] },
  { label: "O I 777/844", range: [775, 846] },
  { label: "Ar I 696-811", range: [695, 812] },
];

export function SpectralQAPanel({ spectrum }: SpectralQAPanelProps) {
  const qa = useMemo(() => analyzeSpectrumQA(spectrum), [spectrum]);

  if (!spectrum) {
    return (
      <section className="panel p-4">
        <div className="mb-2 flex items-center gap-2">
          <Gauge className="h-4 w-4 text-plasma" />
          <h2 className="text-sm font-semibold text-ink">Spectrum QA</h2>
        </div>
        <p className="text-xs leading-relaxed text-slate-600">
          Select a spectrum to check readiness before fitting.
        </p>
      </section>
    );
  }

  const SummaryIcon = statusIcon(qa.overall);

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-plasma" />
          <h2 className="text-sm font-semibold text-ink">Spectrum QA</h2>
        </div>
        <span className={`inline-flex items-center gap-1 border px-2 py-1 text-xs font-semibold ${statusClass(qa.overall)}`} style={{ borderRadius: 999 }}>
          <SummaryIcon className="h-3.5 w-3.5" />
          {qa.overall}
        </span>
      </div>

      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-2">
          {qa.checks.map((check) => {
            const Icon = statusIcon(check.status);
            return (
              <div key={check.label} className="border border-line bg-slate-50 px-2 py-1.5" style={{ borderRadius: 6 }}>
                <div className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-normal text-slate-500">
                  <Icon className={`h-3 w-3 ${iconClass(check.status)}`} />
                  {check.label}
                </div>
                <div className="truncate text-sm font-semibold text-ink" title={check.value}>
                  {check.value}
                </div>
              </div>
            );
          })}
        </div>

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-slate-600">
            Diagnostic Coverage
          </h3>
          <div className="grid gap-1.5">
            {qa.coverage.map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate text-slate-700">{item.label}</span>
                <span className={`shrink-0 border px-2 py-0.5 font-medium ${item.available ? "border-teal-200 bg-teal-50 text-teal-900" : "border-slate-200 bg-slate-50 text-slate-500"}`} style={{ borderRadius: 999 }}>
                  {item.available ? "covered" : "missing"}
                </span>
              </div>
            ))}
          </div>
        </div>

        {qa.notes.length ? (
          <div className="grid gap-2">
            {qa.notes.map((note, index) => (
              <div key={`${note}-${index}`} className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950" style={{ borderRadius: 6 }}>
                {note}
              </div>
            ))}
          </div>
        ) : (
          <div className="border border-teal-200 bg-teal-50 px-3 py-2 text-xs leading-5 text-teal-950" style={{ borderRadius: 6 }}>
            This spectrum looks ready for normal peak and band analysis. Still verify lamp response and calibration for publication work.
          </div>
        )}
      </div>
    </section>
  );
}

function analyzeSpectrumQA(spectrum?: Spectrum | null) {
  if (!spectrum) {
    return { overall: "warning" as QAStatus, checks: [], coverage: [], notes: [] };
  }
  const x = spectrum.wavelength_nm.filter(Number.isFinite);
  const y = spectrum.intensity.filter(Number.isFinite);
  const n = Math.min(x.length, y.length);
  const wave = x.slice(0, n);
  const signal = y.slice(0, n);
  const lo = minOf(wave);
  const hi = maxOf(wave);
  const diffs = wave.slice(1).map((value, index) => value - wave[index]).filter((value) => Number.isFinite(value) && value > 0);
  const medianStep = median(diffs);
  const stepMad = median(diffs.map((value) => Math.abs(value - medianStep)));
  const jitter = medianStep > 0 ? stepMad / medianStep : Infinity;
  const minY = minOf(signal);
  const maxY = maxOf(signal);
  const dynamic = maxY - minY;
  const edgeCount = Math.max(5, Math.floor(signal.length * 0.05));
  const edges = [...signal.slice(0, edgeCount), ...signal.slice(-edgeCount)];
  const edgeNoise = mad(edges);
  const snr = edgeNoise > 0 ? (maxY - median(edges)) / edgeNoise : Infinity;
  const negativeFraction = signal.filter((value) => value < 0).length / Math.max(signal.length, 1);
  const maxTolerance = Math.max(Math.abs(maxY) * 1e-6, 1e-9);
  const clippedFraction = signal.filter((value) => Math.abs(value - maxY) <= maxTolerance).length / Math.max(signal.length, 1);
  const baselineDrift = dynamic > 0 ? Math.abs(median(signal.slice(-edgeCount)) - median(signal.slice(0, edgeCount))) / dynamic : 0;
  const spikeScore = estimateSpikeFraction(signal);

  const checks: QACheck[] = [
    { label: "points", value: n.toLocaleString(), status: n >= 200 ? "good" : n >= 50 ? "warning" : "bad" },
    { label: "range", value: `${format(lo)}-${format(hi)} nm`, status: hi > lo ? "good" : "bad" },
    { label: "median step", value: `${format(medianStep)} nm`, status: medianStep > 0 ? "good" : "bad" },
    { label: "step jitter", value: `${formatPercent(jitter)}`, status: jitter < 0.02 ? "good" : jitter < 0.1 ? "warning" : "bad" },
    { label: "SNR estimate", value: Number.isFinite(snr) ? format(snr) : "very high", status: snr >= 20 ? "good" : snr >= 8 ? "warning" : "bad" },
    { label: "negative points", value: formatPercent(negativeFraction), status: negativeFraction < 0.02 ? "good" : negativeFraction < 0.15 ? "warning" : "bad" },
    { label: "flat-top points", value: formatPercent(clippedFraction), status: clippedFraction < 0.002 ? "good" : clippedFraction < 0.02 ? "warning" : "bad" },
    { label: "edge drift", value: formatPercent(baselineDrift), status: baselineDrift < 0.05 ? "good" : baselineDrift < 0.2 ? "warning" : "bad" },
    { label: "spike estimate", value: formatPercent(spikeScore), status: spikeScore < 0.005 ? "good" : spikeScore < 0.02 ? "warning" : "bad" },
  ];

  const coverage = COVERAGE_WINDOWS.map((item) => ({
    label: item.label,
    available: lo <= item.range[0] && hi >= item.range[1],
  }));
  const notes = checks
    .filter((check) => check.status !== "good")
    .map((check) => noteForCheck(check.label, check.status));
  const overall: QAStatus = checks.some((check) => check.status === "bad")
    ? "bad"
    : checks.some((check) => check.status === "warning")
      ? "warning"
      : "good";
  return { overall, checks, coverage, notes: Array.from(new Set(notes)) };
}

function estimateSpikeFraction(values: number[]) {
  if (values.length < 9) return 0;
  let spikes = 0;
  for (let index = 2; index < values.length - 2; index += 1) {
    const neighborhood = [
      values[index - 2],
      values[index - 1],
      values[index + 1],
      values[index + 2],
    ];
    const localMedian = median(neighborhood);
    const localNoise = mad(neighborhood);
    if (localNoise > 0 && values[index] - localMedian > 8 * localNoise) spikes += 1;
  }
  return spikes / values.length;
}

function noteForCheck(label: string, status: QAStatus) {
  if (label === "step jitter") return "Wavelength spacing is not uniform. Prefer calibration before FWHM, Stark, or molecular profile fits.";
  if (label === "SNR estimate") return status === "bad" ? "SNR is low; peak ratios and fitted temperatures may be unstable." : "SNR is modest; use fit warnings and replicate statistics.";
  if (label === "negative points") return "Negative intensities suggest dark/baseline subtraction offset. Check baseline before ratio or area diagnostics.";
  if (label === "flat-top points") return "Possible saturation or clipping detected. Avoid using clipped peaks for ratios, temperatures, or density.";
  if (label === "edge drift") return "Edge baseline drift is visible. Apply baseline correction before integrated areas or molecular fits.";
  if (label === "spike estimate") return "Spike-like outliers are present. Consider spike removal before peak finding or fitting.";
  if (label === "points") return "Very few points in the spectrum. Narrow line-shape fits may be under-sampled.";
  return `${label} needs review.`;
}

function median(values: number[]) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function minOf(values: number[]) {
  return values.reduce((best, value) => Math.min(best, value), Number.POSITIVE_INFINITY);
}

function maxOf(values: number[]) {
  return values.reduce((best, value) => Math.max(best, value), Number.NEGATIVE_INFINITY);
}

function mad(values: number[]) {
  const center = median(values);
  return median(values.map((value) => Math.abs(value - center))) * 1.4826;
}

function format(value: number) {
  if (!Number.isFinite(value)) return "";
  if (Math.abs(value) >= 1000 || (Math.abs(value) < 0.01 && value !== 0)) return value.toExponential(2);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPercent(value: number) {
  if (!Number.isFinite(value)) return "";
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`;
}

function statusIcon(status: QAStatus) {
  if (status === "good") return CheckCircle2;
  if (status === "bad") return XCircle;
  return AlertTriangle;
}

function statusClass(status: QAStatus) {
  if (status === "good") return "border-teal-200 bg-teal-50 text-teal-900";
  if (status === "bad") return "border-red-200 bg-red-50 text-red-900";
  return "border-amber-200 bg-amber-50 text-amber-950";
}

function iconClass(status: QAStatus) {
  if (status === "good") return "text-teal-700";
  if (status === "bad") return "text-red-700";
  return "text-amber-700";
}
