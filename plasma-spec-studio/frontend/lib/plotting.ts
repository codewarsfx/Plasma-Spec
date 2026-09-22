import type { FitResult, Spectrum } from "./types";

export type PlotSeries = {
  x: number[];
  y: number[];
  name: string;
  color?: string;
  dash?: "solid" | "dot" | "dash";
};

export function spectrumToSeries(spectrum: Spectrum, name = spectrum.filename): PlotSeries {
  return {
    x: spectrum.wavelength_nm,
    y: spectrum.intensity,
    name,
    color: "#0066ff",
  };
}

export function fitResultToSeries(result: FitResult): PlotSeries[] {
  const series: PlotSeries[] = [];
  if (result.measured_curve?.length) {
    series.push({
      x: result.measured_curve.map((point) => point.wavelength_nm),
      y: result.measured_curve.map((point) => point.value),
      name: "Measured",
      color: "#0066ff",
    });
  }
  if (result.fit_curve?.length) {
    series.push({
      x: result.fit_curve.map((point) => point.wavelength_nm),
      y: result.fit_curve.map((point) => point.value),
      name: "Fit",
      color: "#4338ca",
    });
  }
  if (result.baseline_curve?.length) {
    series.push({
      x: result.baseline_curve.map((point) => point.wavelength_nm),
      y: result.baseline_curve.map((point) => point.value),
      name: "Baseline",
      color: "#b7791f",
      dash: "dash",
    });
  }
  return series;
}

export function flattenFitResult(result: FitResult): Record<string, unknown> {
  return {
    filename: result.filename,
    diagnostic: result.diagnostic,
    fit_quality: result.fit_quality,
    ...prefixKeys(result.metadata ?? {}, "metadata_"),
    ...result.parameters,
    ...prefixKeys(result.metrics ?? {}, "metric_"),
  };
}

function prefixKeys(source: Record<string, unknown>, prefix: string) {
  return Object.fromEntries(Object.entries(source).map(([key, value]) => [`${prefix}${key}`, value]));
}
