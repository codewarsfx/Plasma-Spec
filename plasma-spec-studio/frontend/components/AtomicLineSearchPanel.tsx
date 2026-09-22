"use client";

import { Database, Library, Loader2, Plus, RefreshCw, Search, Upload } from "lucide-react";
import { ChangeEvent, useEffect, useState } from "react";
import {
  getAtomicCatalogSummary,
  listAtomicSpecies,
  refreshAtomicFromNist,
  searchAtomicLines,
  uploadAtomicOverrides,
} from "@/lib/api";
import { toast } from "@/components/Toast";
import type { AtomicCatalogSummary, AtomicLine, PeakListEntry } from "@/lib/types";

type AtomicLineSearchPanelProps = {
  onAddPeak?: (peak: PeakListEntry) => void;
};

const DEFAULT_NIST_SPECIES =
  "H I, He I, He II, Ar I, Ar II, O I, O II, N I, N II, C I, C II, Ne I, Ne II, Kr I, Xe I, Hg I";

export function AtomicLineSearchPanel({ onAddPeak }: AtomicLineSearchPanelProps) {
  const [speciesOptions, setSpeciesOptions] = useState<Array<{ species: string; line_count: number }>>([]);
  const [summary, setSummary] = useState<AtomicCatalogSummary | null>(null);
  const [species, setSpecies] = useState<string>("");
  const [wavelengthMin, setWavelengthMin] = useState<string>("");
  const [wavelengthMax, setWavelengthMax] = useState<string>("");
  const [near, setNear] = useState<string>("");
  const [tolerance, setTolerance] = useState<string>("0.5");
  const [requireEinstein, setRequireEinstein] = useState(false);
  const [nistSpecies, setNistSpecies] = useState(DEFAULT_NIST_SPECIES);
  const [nistMin, setNistMin] = useState("200");
  const [nistMax, setNistMax] = useState("1100");
  const [nistMode, setNistMode] = useState<"append" | "replace">("append");
  const [nistRequireEinstein, setNistRequireEinstein] = useState(false);
  const [results, setResults] = useState<AtomicLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reloadCatalogMetadata();
  }, []);

  async function reloadCatalogMetadata() {
    try {
      const [speciesResponse, summaryResponse] = await Promise.all([
        listAtomicSpecies(),
        getAtomicCatalogSummary(),
      ]);
      setSpeciesOptions(speciesResponse.species);
      setSummary(summaryResponse);
    } catch {
      setSpeciesOptions([]);
      setSummary(null);
    }
  }

  async function runSearch() {
    setBusy(true);
    setError(null);
    try {
      const params: Parameters<typeof searchAtomicLines>[0] = {
        max_results: 50,
        require_einstein: requireEinstein,
      };
      if (species) params.species = [species];
      if (wavelengthMin) params.wavelength_min_nm = Number(wavelengthMin);
      if (wavelengthMax) params.wavelength_max_nm = Number(wavelengthMax);
      if (near) {
        params.near_nm = Number(near);
        params.tolerance_nm = Number(tolerance);
      }
      const response = await searchAtomicLines(params);
      setResults(response.results);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Atomic line search failed");
    } finally {
      setBusy(false);
    }
  }

  async function refreshFromNist() {
    const speciesList = nistSpecies
      .split(/[,;\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (speciesList.length === 0) {
      toast.error("NIST refresh needs species", "Enter at least one species such as Ar I or O I.");
      return;
    }
    setRefreshBusy(true);
    try {
      const response = await refreshAtomicFromNist({
        species: speciesList,
        wavelength_min_nm: nistMin ? Number(nistMin) : null,
        wavelength_max_nm: nistMax ? Number(nistMax) : null,
        mode: nistMode,
        require_transition_probabilities: nistRequireEinstein,
        max_lines_per_species: 25_000,
      });
      setSummary(response.catalog_summary);
      await reloadCatalogMetadata();
      const failures = response.failures.length;
      const message = `${response.imported_rows.toLocaleString()} NIST rows fetched; catalog now has ${response.catalog_summary.line_count.toLocaleString()} lines.`;
      if (failures > 0) {
        toast.warning("NIST refresh partially completed", `${message} ${failures} species failed.`);
      } else {
        toast.success("NIST refresh complete", message);
      }
    } catch (exc) {
      toast.error("NIST refresh failed", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setRefreshBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center gap-2">
        <Library className="h-4 w-4 text-plasma" />
        <h2 className="text-sm font-semibold text-ink">Line Database</h2>
        <span className="ml-auto text-xs text-slate-500">
          {summary
            ? `${summary.line_count.toLocaleString()} lines · ${summary.species_count} species`
            : "NIST-derived"}
        </span>
        <UploadOverridesButton onUploaded={reloadCatalogMetadata} />
      </div>
      <p className="mb-3 text-xs leading-relaxed text-slate-600">
        Search NIST lines by species / range / proximity. Click <strong>+</strong> to add the line
        to the Wavelength List above.
      </p>
      <div className="mb-3 border-b border-line pb-3">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-ink">
          <Database className="h-3.5 w-3.5 text-plasma" />
          Official NIST ASD refresh
          {summary?.source_counts?.nist_live ? (
            <span className="ml-auto font-normal text-slate-500">
              {summary.source_counts.nist_live.toLocaleString()} live-cache rows
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-2 grid gap-1">
            <span className="control-label">Species</span>
            <input
              className="field"
              value={nistSpecies}
              onChange={(event) => setNistSpecies(event.target.value)}
            />
          </label>
          <label className="grid gap-1">
            <span className="control-label">Min nm</span>
            <input className="field" type="number" value={nistMin} onChange={(event) => setNistMin(event.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className="control-label">Max nm</span>
            <input className="field" type="number" value={nistMax} onChange={(event) => setNistMax(event.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className="control-label">Mode</span>
            <select className="field" value={nistMode} onChange={(event) => setNistMode(event.target.value as "append" | "replace")}>
              <option value="append">Append</option>
              <option value="replace">Replace live cache</option>
            </select>
          </label>
          <label className="flex items-center gap-2 pt-6 text-xs text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 accent-teal-700"
              checked={nistRequireEinstein}
              onChange={(event) => setNistRequireEinstein(event.target.checked)}
            />
            TP only
          </label>
        </div>
        <button className="text-button mt-2" onClick={refreshFromNist} disabled={refreshBusy}>
          {refreshBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh from NIST
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 grid gap-1">
          <span className="control-label">Species</span>
          <select className="field" value={species} onChange={(event) => setSpecies(event.target.value)}>
            <option value="">Any</option>
            {speciesOptions.map((option) => (
              <option key={option.species} value={option.species}>
                {option.species} ({option.line_count})
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="control-label">Min nm</span>
          <input
            className="field"
            type="number"
            step="0.1"
            value={wavelengthMin}
            onChange={(event) => setWavelengthMin(event.target.value)}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Max nm</span>
          <input
            className="field"
            type="number"
            step="0.1"
            value={wavelengthMax}
            onChange={(event) => setWavelengthMax(event.target.value)}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Near nm</span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={near}
            onChange={(event) => setNear(event.target.value)}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Tol nm</span>
          <input
            className="field"
            type="number"
            step="0.05"
            value={tolerance}
            onChange={(event) => setTolerance(event.target.value)}
          />
        </label>
        <label className="col-span-2 flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-teal-700"
            checked={requireEinstein}
            onChange={(event) => setRequireEinstein(event.target.checked)}
          />
          Require Einstein A_ki (only Boltzmann-ready lines)
        </label>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button className="primary-button" onClick={runSearch} disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Search
        </button>
        <span className="text-xs text-slate-500">{results.length} result{results.length === 1 ? "" : "s"}</span>
      </div>

      {error ? (
        <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
          {error}
        </div>
      ) : null}

      {results.length > 0 ? (
        <div className="mt-3 max-h-80 overflow-auto border border-line" style={{ borderRadius: 6 }}>
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white text-[11px] uppercase tracking-normal text-slate-600">
              <tr>
                <th className="border-b border-line px-2 py-1.5">Species</th>
                <th className="border-b border-line px-2 py-1.5 text-right">λ air (nm)</th>
                <th className="border-b border-line px-2 py-1.5 text-right">A_ki (s⁻¹)</th>
                <th className="border-b border-line px-2 py-1.5">Transition</th>
                <th className="border-b border-line px-2 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {results.map((line, index) => (
                <tr key={`${line.species}-${line.wavelength_air_nm}-${index}`} className="odd:bg-white even:bg-slate-50">
                  <td className="border-b border-line px-2 py-1.5 font-medium text-ink">{line.species}</td>
                  <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                    {line.wavelength_air_nm.toFixed(3)}
                  </td>
                  <td className="border-b border-line px-2 py-1.5 text-right tabular-nums">
                    {line.A_ki_s_1 ? line.A_ki_s_1.toExponential(2) : ""}
                  </td>
                  <td className="border-b border-line px-2 py-1.5 text-slate-700">
                    {line.transition ?? ""}
                  </td>
                  <td className="border-b border-line px-2 py-1.5 text-right">
                    {onAddPeak ? (
                      <button
                        className="icon-button h-7 w-7"
                        title="Add to wavelength list"
                        onClick={() =>
                          onAddPeak({
                            label: `${line.species} ${line.wavelength_air_nm.toFixed(2)}`,
                            center_nm: line.wavelength_air_nm,
                            species: line.species,
                            transition: line.transition ?? undefined,
                          })
                        }
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function UploadOverridesButton({ onUploaded }: { onUploaded?: () => void }) {
  const [busy, setBusy] = useState(false);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const response = await uploadAtomicOverrides(file, "append");
      toast.success(
        "Atomic overrides merged",
        `${response.appended_rows} new rows; catalog now has ${(response.catalog_summary as { line_count: number }).line_count} lines.`,
      );
      onUploaded?.();
    } catch (exc) {
      toast.error("Upload failed", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setBusy(false);
      // Reset so re-uploading the same file works
      event.target.value = "";
    }
  }

  return (
    <label
      className="inline-flex h-7 w-7 cursor-pointer items-center justify-center border border-line bg-white text-slate-700 transition hover:bg-slate-50"
      style={{ borderRadius: 6 }}
      title="Upload a CSV with extra atomic lines (NIST ASD export, same schema as the bundled catalog). Merged into user_overrides.csv."
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
      <input
        className="hidden"
        type="file"
        accept=".csv,.tsv,.txt"
        onChange={handleFile}
      />
    </label>
  );
}
