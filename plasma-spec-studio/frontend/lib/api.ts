import type {
  AtomicLine,
  AtomicCatalogSummary,
  AtomicForwardFitRequest,
  AtomicNistRefreshRequest,
  AtomicNistRefreshResponse,
  BatchRunResult,
  ElectronDensityRequest,
  ElectronDensityResult,
  FitResult,
  MolecularDatabaseEntry,
  PeakListEntry,
  PeakListResult,
  PreprocessingOperation,
  Recipe,
  Spectrum,
  SpectrumSummary,
} from "./types";

import { getCachedAccessToken } from "./supabase/client";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getCachedAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? { ...authHeaders(), ...(init.headers ?? {}) }
      : { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail ?? JSON.stringify(data);
    } catch {
      // Keep the status text.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function uploadSpectra(files: File[], metadata: Record<string, unknown> = {}) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  if (Object.keys(metadata).length > 0) {
    form.append("metadata_json", JSON.stringify(metadata));
  }
  return request<SpectrumSummary[]>("/api/spectra/upload", { method: "POST", body: form });
}

export function listSpectra() {
  return request<SpectrumSummary[]>("/api/spectra");
}

export function getSpectrum(id: string) {
  return request<Spectrum>(`/api/spectra/${id}`);
}

export function preprocessSpectrum(
  spectrumId: string,
  operations: PreprocessingOperation[],
  saveAsNew = false,
) {
  return request<{ spectrum: Spectrum; mode: "preview" | "saved" }>("/api/preprocess", {
    method: "POST",
    body: JSON.stringify({ spectrum_id: spectrumId, operations, save_as_new: saveAsNew }),
  });
}

export function fitHbeta(payload: Record<string, unknown>) {
  return request<FitResult>("/api/fit/hbeta", { method: "POST", body: JSON.stringify(payload) });
}

export function fitOh(payload: Record<string, unknown>) {
  return request<FitResult>("/api/fit/oh", { method: "POST", body: JSON.stringify(payload) });
}

export function fitN2(payload: Record<string, unknown>) {
  return request<FitResult>("/api/fit/n2", { method: "POST", body: JSON.stringify(payload) });
}

export function fitMolecular(payload: Record<string, unknown>) {
  return request<FitResult>("/api/fit/molecular", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fitMolecularStateByState(payload: Record<string, unknown>) {
  return request<FitResult>("/api/fit/molecular/state-by-state", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fitAtomicForward(payload: AtomicForwardFitRequest) {
  return request<FitResult>("/api/fit/atomic-forward", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzePeak(payload: Record<string, unknown>) {
  return request<FitResult>("/api/analyze/peak-area", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function computeElectronDensity(payload: ElectronDensityRequest) {
  return request<ElectronDensityResult>("/api/diagnostics/electron-density", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzePeakList(payload: {
  spectrum_id: string;
  peaks: PeakListEntry[];
  preprocessing?: PreprocessingOperation[];
  default_half_width_nm?: number;
  default_fit_model?: "gaussian" | "lorentzian" | "voigt" | null;
}) {
  return request<PeakListResult>("/api/analyze/peak-list", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listMolecularDatabases() {
  return request<{ root: string; species: MolecularDatabaseEntry[] }>(
    "/api/databases/molecular",
  );
}

export function searchAtomicLines(params: {
  species?: string[];
  wavelength_min_nm?: number;
  wavelength_max_nm?: number;
  near_nm?: number;
  tolerance_nm?: number;
  require_einstein?: boolean;
  energy_upper_max_cm1?: number;
  max_results?: number;
}) {
  const search = new URLSearchParams();
  if (params.species) params.species.forEach((s) => search.append("species", s));
  for (const [key, value] of Object.entries(params)) {
    if (key === "species" || value === undefined || value === null) continue;
    search.append(key, String(value));
  }
  const queryString = search.toString();
  const path = `/api/databases/atomic/search${queryString ? `?${queryString}` : ""}`;
  return request<{ count: number; results: AtomicLine[] }>(path);
}

export function listAtomicSpecies() {
  return request<{ species: Array<{ species: string; line_count: number }> }>(
    "/api/databases/atomic/species",
  );
}

export function getAtomicCatalogSummary() {
  return request<AtomicCatalogSummary>("/api/databases/atomic/summary");
}

export function refreshAtomicFromNist(payload: AtomicNistRefreshRequest) {
  return request<AtomicNistRefreshResponse>("/api/databases/atomic/refresh", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function uploadAtomicOverrides(file: File, mode: "append" | "replace" = "append") {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  return request<{
    status: string;
    appended_rows: number;
    total_overrides: number;
    catalog_summary: Record<string, unknown>;
    overrides_path: string;
  }>("/api/databases/atomic/overrides", { method: "POST", body: form });
}

export function identifyLines(payload: Record<string, unknown>) {
  return request<FitResult>("/api/identify-lines", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveRecipe(recipe: Recipe) {
  return request<Recipe>("/api/recipes", { method: "POST", body: JSON.stringify(recipe) });
}

export function listRecipes() {
  return request<Recipe[]>("/api/recipes");
}

export function deleteRecipe(id: string) {
  return request<{ deleted: string }>(`/api/recipes/${id}`, { method: "DELETE" });
}

export function runBatch(spectrumIds: string[], recipe: Recipe) {
  return request<BatchRunResult>("/api/batch/run", {
    method: "POST",
    body: JSON.stringify({ spectrum_ids: spectrumIds, recipe }),
  });
}

export function startBatchStreamed(spectrumIds: string[], recipe: Recipe) {
  return request<{ batch_id: string; total: number; recipe_kind: string }>(
    "/api/batch/start",
    {
      method: "POST",
      body: JSON.stringify({ spectrum_ids: spectrumIds, recipe }),
    },
  );
}

export function getBatchResult(batchId: string) {
  return request<BatchRunResult>(`/api/batch/${batchId}/result`);
}

export function batchStreamUrl(batchId: string) {
  // EventSource can't set an Authorization header, so the token (when
  // present) rides along as a query param; app/auth.py's `authenticated`
  // dependency accepts either.
  const token = getCachedAccessToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/batch/${batchId}/stream${query}`;
}

export function exportResult(result: FitResult, formats: Array<"json" | "csv" | "png">) {
  return request<{ exports: Record<string, { export_id: string; path: string; kind: string }> }>(
    "/api/exports/result",
    { method: "POST", body: JSON.stringify({ result, formats }) },
  );
}

export function exportReport(result: FitResult, formats: Array<"html" | "pdf">) {
  return request<{ exports: Record<string, { export_id: string; path: string; kind: string }> }>(
    "/api/reports/result",
    { method: "POST", body: JSON.stringify({ result, formats }) },
  );
}

export function listResults() {
  return request<FitResult[]>("/api/results");
}

export function exportUrl(exportId: string) {
  // Same reasoning as batchStreamUrl(): this is used as a plain <a href> /
  // window.open() target, not a fetch() through request(), so it can't
  // carry an Authorization header either.
  const token = getCachedAccessToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/exports/${exportId}${query}`;
}
