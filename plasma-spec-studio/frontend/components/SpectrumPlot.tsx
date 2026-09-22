"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { PlotSeries } from "@/lib/plotting";
import { useThemePalette } from "@/lib/useThemePalette";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as any;

type SpectrumPlotProps = {
  series: PlotSeries[];
  title?: string;
  height?: number;
  selectedWindow?: [number, number];
  yTitle?: string;
};

export function SpectrumPlot({
  series,
  title = "Spectrum",
  height = 440,
  selectedWindow,
  yTitle = "Intensity (a.u.)",
}: SpectrumPlotProps) {
  const palette = useThemePalette();
  const data = useMemo(
    () =>
      series.map((item) => ({
        type: "scatter",
        mode: "lines",
        x: item.x,
        y: item.y,
        name: item.name,
        line: { color: item.color, width: 1.8, dash: item.dash ?? "solid" },
        hovertemplate: "λ %{x:.3f} nm<br>%{y:.4g}<extra>%{fullData.name}</extra>",
      })),
    [series],
  );

  const shapes = selectedWindow
    ? [
        {
          type: "rect",
          xref: "x",
          yref: "paper",
          x0: selectedWindow[0],
          x1: selectedWindow[1],
          y0: 0,
          y1: 1,
          fillcolor: "rgba(15, 118, 110, 0.08)",
          line: { color: palette.plasma, width: 1 },
          layer: "below",
        },
      ]
    : [];

  return (
    <div className="panel overflow-hidden">
      <Plot
        data={data}
        layout={{
          title: { text: title, font: { size: 15 } },
          font: { color: palette.text },
          height,
          margin: { l: 62, r: 24, t: 44, b: 54 },
          paper_bgcolor: palette.paper,
          plot_bgcolor: palette.plot,
          xaxis: {
            title: "Wavelength (nm)",
            showgrid: true,
            gridcolor: palette.grid,
            zeroline: false,
          },
          yaxis: {
            title: yTitle,
            showgrid: true,
            gridcolor: palette.grid,
            zeroline: false,
          },
          legend: { orientation: "h", x: 0, y: 1.12 },
          hovermode: "x unified",
          shapes,
        }}
        config={{
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
          toImageButtonOptions: {
            format: "png",
            filename: "plasma-spec-spectrum",
            height,
            width: 960,
            scale: 2,
          },
        }}
        style={{ width: "100%", height }}
        useResizeHandler
      />
    </div>
  );
}
