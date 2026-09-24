"use client";

import { Loader2, Trash2 } from "lucide-react";
import { MouseEvent, useState } from "react";
import { deleteSpectrum } from "@/lib/api";
import { toast } from "@/components/Toast";
import type { SpectrumSummary } from "@/lib/types";

type MetadataTableProps = {
  spectra: SpectrumSummary[];
  selectedId?: string;
  onSelect?: (id: string) => void;
  onDeleted?: (id: string) => void;
};

export function MetadataTable({ spectra, selectedId, onSelect, onDeleted }: MetadataTableProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(spectrum: SpectrumSummary, event: MouseEvent) {
    event.stopPropagation();
    if (!window.confirm(`Delete "${spectrum.filename}"? This also deletes any fit results for it. This can't be undone.`)) {
      return;
    }
    setDeletingId(spectrum.id);
    try {
      await deleteSpectrum(spectrum.id);
      onDeleted?.(spectrum.id);
      toast.success("Deleted", spectrum.filename);
    } catch (exc) {
      toast.error("Delete failed", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setDeletingId(null);
    }
  }
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Spectra</h2>
      </div>
      <div className="max-h-[460px] overflow-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-normal text-slate-600">
            <tr>
              <th className="border-b border-line px-3 py-2">File</th>
              <th className="border-b border-line px-3 py-2">Range</th>
              <th className="border-b border-line px-3 py-2">Gas</th>
              <th className="border-b border-line px-3 py-2">Pulse</th>
              <th className="border-b border-line px-3 py-2">N</th>
              <th className="border-b border-line px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {spectra.map((spectrum) => (
              <tr
                key={spectrum.id}
                className={`cursor-pointer hover:bg-teal-50 ${
                  selectedId === spectrum.id ? "bg-teal-50" : "bg-white"
                }`}
                onClick={() => onSelect?.(spectrum.id)}
              >
                <td className="border-b border-line px-3 py-2 font-medium text-ink">{spectrum.filename}</td>
                <td className="border-b border-line px-3 py-2 text-slate-600">
                  {formatRange(spectrum.wavelength_min_nm, spectrum.wavelength_max_nm)}
                </td>
                <td className="border-b border-line px-3 py-2 text-slate-600">{spectrum.metadata?.gas ?? ""}</td>
                <td className="border-b border-line px-3 py-2 text-slate-600">
                  {spectrum.metadata?.pulse_mode ?? ""}
                </td>
                <td className="border-b border-line px-3 py-2 text-slate-600">
                  {spectrum.metadata?.n_cycles ?? ""}
                </td>
                <td className="border-b border-line px-3 py-2 text-right">
                  <button
                    className="inline-flex h-6 w-6 items-center justify-center text-slate-400 transition hover:text-red-900"
                    title="Delete spectrum"
                    disabled={deletingId === spectrum.id}
                    onClick={(event) => handleDelete(spectrum, event)}
                  >
                    {deletingId === spectrum.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </td>
              </tr>
            ))}
            {spectra.length === 0 ? (
              <tr>
                <td className="px-3 py-8 text-center text-sm text-slate-500" colSpan={6}>
                  No spectra loaded
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatRange(min?: number | null, max?: number | null) {
  if (min == null || max == null) return "";
  return `${min.toFixed(1)}-${max.toFixed(1)} nm`;
}

