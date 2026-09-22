"use client";

import type { FitResult } from "@/lib/types";
import { SpectrumPlot } from "./SpectrumPlot";

type ResidualPlotProps = {
  result?: FitResult | null;
};

export function ResidualPlot({ result }: ResidualPlotProps) {
  if (!result?.residual_curve?.length) {
    return (
      <section className="panel p-4">
        <h2 className="text-sm font-semibold text-ink">Residuals</h2>
        <p className="mt-3 text-sm text-slate-500">Residuals appear after a fit.</p>
      </section>
    );
  }
  return (
    <SpectrumPlot
      title="Residuals"
      height={260}
      yTitle="Residual (a.u.)"
      series={[
        {
          x: result.residual_curve.map((point) => point.wavelength_nm),
          y: result.residual_curve.map((point) => point.value),
          name: "Residual",
          color: "#be123c",
        },
      ]}
    />
  );
}

