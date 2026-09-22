"use client";

import { ChangeEvent, useState } from "react";
import { FolderUp, Loader2, Upload } from "lucide-react";
import { uploadSpectra } from "@/lib/api";
import type { SpectrumSummary } from "@/lib/types";

type SpectrumUploaderProps = {
  onUploaded: (spectra: SpectrumSummary[]) => void;
};

export function SpectrumUploader({ onUploaded }: SpectrumUploaderProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [metadataText, setMetadataText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  async function handleUpload() {
    setBusy(true);
    setError(null);
    try {
      const metadata = metadataText.trim() ? JSON.parse(metadataText) : {};
      const saved = await uploadSpectra(files, metadata);
      onUploaded(saved);
      setFiles([]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Spectrum Import</h2>
        <span className="text-xs text-slate-500">{files.length} selected</span>
      </div>
      <div className="grid gap-3">
        <label className="grid gap-1">
          <span className="control-label">Spectra files</span>
          <input
            className="field h-auto py-2"
            type="file"
            multiple
            accept=".csv,.txt,.tsv,.asc,.dat,.xlsx,.xlsm,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
            onChange={handleFiles}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Shared metadata JSON</span>
          <textarea
            className="field min-h-24 py-2 font-mono text-xs"
            value={metadataText}
            onChange={(event) => setMetadataText(event.target.value)}
          />
        </label>
        {error ? (
          <div className="border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
            {error}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button className="primary-button" onClick={handleUpload} disabled={busy || files.length === 0}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Upload
          </button>
          <label className="text-button cursor-pointer">
            <FolderUp className="h-4 w-4" />
            Folder
            <input
              className="hidden"
              type="file"
              multiple
              // @ts-expect-error Browser folder upload attribute.
              webkitdirectory=""
              onChange={handleFiles}
            />
          </label>
        </div>
      </div>
    </section>
  );
}

