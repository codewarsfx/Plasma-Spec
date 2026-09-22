"use client";

import { Download, FileJson, FileSpreadsheet, FileText, Image as ImageIcon, Loader2 } from "lucide-react";
import { useState } from "react";
import { exportReport, exportResult, exportUrl } from "@/lib/api";
import { toast } from "@/components/Toast";
import type { FitResult } from "@/lib/types";

type ExportPanelProps = {
  result?: FitResult | null;
};

export function ExportPanel({ result }: ExportPanelProps) {
  const [links, setLinks] = useState<Array<{ label: string; url: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runExport() {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      const exported = await exportResult(result, ["json", "csv", "png"]);
      const next = Object.entries(exported.exports).map(([label, value]) => ({
        label: label.toUpperCase(),
        url: exportUrl(value.export_id),
      }));
      setLinks(next);
      toast.success(`Exported ${next.length} file${next.length === 1 ? "" : "s"}`, next.map((l) => l.label).join(", "));
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Export failed";
      setError(message);
      toast.error("Export failed", message);
    } finally {
      setBusy(false);
    }
  }

  async function runReport(formats: Array<"html" | "pdf">) {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      const exported = await exportReport(result, formats);
      const newLinks = Object.entries(exported.exports).map(([label, value]) => ({
        label: `Report (${label.toUpperCase()})`,
        url: exportUrl(value.export_id),
      }));
      setLinks((current) => [...current, ...newLinks]);
      toast.success(`Report generated`, formats.join(", ").toUpperCase());
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Report failed";
      setError(message);
      toast.error("Report failed", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Exports &amp; reports</h2>
        <div className="flex flex-wrap items-center gap-2">
          <button className="primary-button" onClick={runExport} disabled={!result || busy} title="Export JSON, CSV, and PNG plot">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Export raw
          </button>
          <button className="text-button" onClick={() => runReport(["html"])} disabled={!result || busy} title="Generate a self-contained HTML report with parameters + plot + assumptions">
            <FileText className="h-4 w-4" />
            HTML report
          </button>
          <button className="text-button" onClick={() => runReport(["pdf"])} disabled={!result || busy} title="Generate a printable PDF report">
            <FileText className="h-4 w-4" />
            PDF
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {links.map((link) => (
          <a key={link.label + link.url} className="text-button" href={link.url} target="_blank" rel="noreferrer">
            {iconFor(link.label)}
            {link.label}
          </a>
        ))}
        {links.length === 0 ? <span className="text-sm text-slate-500">No files exported yet</span> : null}
      </div>
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
    </section>
  );
}

function iconFor(label: string) {
  if (label === "JSON") return <FileJson className="h-4 w-4" />;
  if (label === "CSV") return <FileSpreadsheet className="h-4 w-4" />;
  return <ImageIcon className="h-4 w-4" />;
}

