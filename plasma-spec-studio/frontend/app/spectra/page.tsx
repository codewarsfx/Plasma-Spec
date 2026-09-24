"use client";

import { useEffect, useMemo, useState } from "react";
import { Eye, RefreshCw } from "lucide-react";
import { getSpectrum, listSpectra } from "@/lib/api";
import { spectrumToSeries } from "@/lib/plotting";
import type { Spectrum, SpectrumSummary } from "@/lib/types";
import { LegacyPageShell } from "@/components/LegacyPageShell";
import { MetadataTable } from "@/components/MetadataTable";
import { SpectrumPlot } from "@/components/SpectrumPlot";
import { SpectrumUploader } from "@/components/SpectrumUploader";

export default function SpectraPage() {
  const [spectra, setSpectra] = useState<SpectrumSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState<Record<string, Spectrum>>({});
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setSpectra(await listSpectra());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load spectra");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function selectSpectrum(id: string) {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
    if (!loaded[id]) {
      try {
        const spectrum = await getSpectrum(id);
        setLoaded((current) => ({ ...current, [id]: spectrum }));
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Could not load spectrum");
      }
    }
  }

  const series = useMemo(
    () =>
      Array.from(selectedIds)
        .map((id) => loaded[id])
        .filter(Boolean)
        .map((spectrum, index) => ({ ...spectrumToSeries(spectrum), color: colors[index % colors.length] })),
    [loaded, selectedIds],
  );

  return (
    <LegacyPageShell
      title="Spectra"
      description="Bulk upload, metadata table, and overlay view. The Studio workstation provides the same upload + overlay plus interactive analysis tools."
    >
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="grid content-start gap-4">
          <SpectrumUploader onUploaded={(uploaded) => {
            setSpectra((current) => [...uploaded, ...current]);
            refresh();
          }} />
          <button className="text-button w-fit" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </div>
        <div className="grid gap-4">
          <MetadataTable
            spectra={spectra}
            selectedId={Array.from(selectedIds)[0]}
            onSelect={selectSpectrum}
            onDeleted={(id) => {
              setSpectra((current) => current.filter((item) => item.id !== id));
              setSelectedIds((current) => {
                if (!current.has(id)) return current;
                const next = new Set(current);
                next.delete(id);
                return next;
              });
              setLoaded((current) => {
                if (!(id in current)) return current;
                const next = { ...current };
                delete next[id];
                return next;
              });
            }}
          />
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Eye className="h-4 w-4" />
            {selectedIds.size} overlay{selectedIds.size === 1 ? "" : "s"} selected
          </div>
          <SpectrumPlot series={series} title="Raw Spectra Overlay" />
        </div>
      </div>
    </LegacyPageShell>
  );
}

const colors = ["#0066ff", "#4338ca", "#b7791f", "#be123c", "#0369a1", "#166534"];
