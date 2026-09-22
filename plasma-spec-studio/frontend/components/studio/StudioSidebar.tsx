"use client";

import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Upload,
} from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { listSpectra, uploadSpectra } from "@/lib/api";
import { toast } from "@/components/Toast";
import type { SpectrumSummary } from "@/lib/types";

type GroupKey =
  | "none"
  | "pulse_frequency_khz"
  | "burst_period_ms"
  | "n_cycles"
  | "gas"
  | "date"
  | "replicate";

const GROUP_OPTIONS: Array<{ value: GroupKey; label: string }> = [
  { value: "none", label: "No grouping" },
  { value: "pulse_frequency_khz", label: "Pulse frequency (kHz)" },
  { value: "burst_period_ms", label: "Burst period (ms)" },
  { value: "n_cycles", label: "Number of cycles" },
  { value: "gas", label: "Gas" },
  { value: "date", label: "Date" },
  { value: "replicate", label: "Replicate" },
];

type StudioSidebarProps = {
  spectra: SpectrumSummary[];
  onSpectraChange: (spectra: SpectrumSummary[]) => void;
  selectedId?: string;
  overlayIds: Set<string>;
  onSelectSpectrum: (id: string) => void;
  onToggleOverlay: (id: string) => void;
};

export function StudioSidebar({
  spectra,
  onSpectraChange,
  selectedId,
  overlayIds,
  onSelectSpectrum,
  onToggleOverlay,
}: StudioSidebarProps) {
  const [search, setSearch] = useState("");
  const [groupKey, setGroupKey] = useState<GroupKey>("pulse_frequency_khz");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function refresh() {
    try {
      onSpectraChange(await listSpectra());
    } catch (exc) {
      setUploadError(exc instanceof Error ? exc.message : "Refresh failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    setUploadBusy(true);
    setUploadError(null);
    try {
      const uploaded = await uploadSpectra(files);
      await refresh();
      toast.success(
        `Uploaded ${uploaded.length} file${uploaded.length === 1 ? "" : "s"}`,
        uploaded.map((s) => s.filename).slice(0, 3).join(", "),
      );
      // reset input so re-uploading the same file works
      event.target.value = "";
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Upload failed";
      setUploadError(message);
      toast.error("Upload failed", message);
    } finally {
      setUploadBusy(false);
    }
  }

  const filteredSpectra = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return spectra;
    return spectra.filter((spectrum) => {
      if (spectrum.filename.toLowerCase().includes(term)) return true;
      return Object.values(spectrum.metadata ?? {})
        .some((value) => value != null && String(value).toLowerCase().includes(term));
    });
  }, [spectra, search]);

  const groupedSpectra = useMemo(() => {
    if (groupKey === "none") {
      return new Map<string, SpectrumSummary[]>([["All spectra", filteredSpectra]]);
    }
    const map = new Map<string, SpectrumSummary[]>();
    for (const spectrum of filteredSpectra) {
      const raw = spectrum.metadata?.[groupKey];
      const key = raw == null ? "(no value)" : String(raw);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(spectrum);
    }
    // Sort group keys for stability (numeric keys numeric, otherwise alpha)
    return new Map(
      Array.from(map.entries()).sort(([a], [b]) => {
        const aNum = Number(a);
        const bNum = Number(b);
        if (Number.isFinite(aNum) && Number.isFinite(bNum)) return aNum - bNum;
        return a.localeCompare(b);
      }),
    );
  }, [filteredSpectra, groupKey]);

  function toggleGroup(key: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="flex h-full flex-col border-r border-line bg-white">
      <div className="border-b border-line px-3 py-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink">Spectra</h2>
          <div className="flex items-center gap-1">
            <button
              className="icon-button h-7 w-7"
              title="Refresh"
              onClick={refresh}
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <label className="icon-button h-7 w-7 cursor-pointer" title="Upload">
              {uploadBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
              <input
                className="hidden"
                type="file"
                multiple
                accept=".csv,.txt,.tsv,.asc,.dat,.xlsx,.xlsm,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv,text/plain"
                onChange={handleUpload}
                disabled={uploadBusy}
              />
            </label>
          </div>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <input
            className="field h-8 w-full pl-7 text-xs"
            placeholder="Search files or metadata"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-slate-500" />
          <select
            className="field h-7 flex-1 text-xs"
            value={groupKey}
            onChange={(event) => setGroupKey(event.target.value as GroupKey)}
          >
            {GROUP_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {uploadError ? (
          <div className="mt-2 border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-800" style={{ borderRadius: 4 }}>
            {uploadError}
          </div>
        ) : null}
      </div>
      <div className="flex-1 overflow-auto">
        {filteredSpectra.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-slate-500">
            No spectra yet. Use the upload button above.
          </div>
        ) : (
          Array.from(groupedSpectra.entries()).map(([groupName, members]) => {
            const open = !collapsed.has(groupName);
            const groupLabel = groupKey === "none" ? `${members.length}` : `${members.length} files`;
            return (
              <div key={groupName} className="border-b border-line">
                <button
                  className="flex w-full items-center gap-1 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100"
                  onClick={() => toggleGroup(groupName)}
                >
                  {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  <span className="truncate text-left">
                    {groupKey === "none" ? "All spectra" : `${prettyGroup(groupKey)} = ${groupName}`}
                  </span>
                  <span className="ml-auto text-[10px] text-slate-500">{groupLabel}</span>
                </button>
                {open ? (
                  <ul>
                    {members.map((spectrum) => {
                      const isSelected = selectedId === spectrum.id;
                      const isOverlay = overlayIds.has(spectrum.id);
                      return (
                        <li
                          key={spectrum.id}
                          className={`flex items-center gap-2 border-b border-line px-3 py-2 text-xs last:border-b-0 cursor-pointer transition ${
                            isSelected ? "bg-teal-50" : "bg-white hover:bg-slate-50"
                          }`}
                          onClick={() => onSelectSpectrum(spectrum.id)}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium text-ink">{spectrum.filename}</div>
                            <div className="mt-0.5 text-[10px] text-slate-500">
                              {formatRange(spectrum.wavelength_min_nm, spectrum.wavelength_max_nm)}
                              {spectrum.points ? ` · ${spectrum.points} pts` : ""}
                            </div>
                          </div>
                          <button
                            className={`flex h-6 w-6 items-center justify-center transition ${
                              isOverlay ? "text-teal-700" : "text-slate-400 hover:text-slate-700"
                            }`}
                            title={isOverlay ? "Hide overlay" : "Show as overlay"}
                            onClick={(event) => {
                              event.stopPropagation();
                              onToggleOverlay(spectrum.id);
                            }}
                          >
                            {isOverlay ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function prettyGroup(key: string) {
  if (key === "pulse_frequency_khz") return "freq (kHz)";
  if (key === "burst_period_ms") return "burst (ms)";
  if (key === "n_cycles") return "cycles";
  return key;
}

function formatRange(min?: number | null, max?: number | null) {
  if (min == null || max == null) return "";
  return `${min.toFixed(0)}-${max.toFixed(0)} nm`;
}
