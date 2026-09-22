"use client";

import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listMolecularDatabases, saveRecipe } from "@/lib/api";
import { toast } from "@/components/Toast";
import type {
  MolecularDatabaseEntry,
  PeakListEntry,
  Recipe,
  RecipeKind,
} from "@/lib/types";

type RecipeEditorProps = {
  initial?: Recipe;
  onSaved?: (recipe: Recipe) => void;
};

const KIND_LABELS: Record<RecipeKind, string> = {
  peak_list: "Wavelength list (peak areas + Voigt fits)",
  molecular_v2: "Molecular fit (Trot / Tvib via OH, N₂, …)",
  electron_density: "Electron density (Stark / Gigosos H-α)",
  hbeta_voigt: "H-β Voigt (legacy)",
  peak_area: "Single-window peak area (legacy)",
  oh_ax: "OH(A-X) (legacy)",
  n2_cb: "N₂(C-B) (legacy)",
  line_identification: "Atomic line identification (legacy)",
};

function rowId() {
  return Math.random().toString(36).slice(2, 9);
}

const DEFAULT_PEAK_ROWS: (PeakListEntry & { _row: string })[] = [
  { _row: rowId(), label: "H-alpha", center_nm: 656.279, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
  { _row: rowId(), label: "H-beta", center_nm: 486.135, half_width_nm: 1.5, fit_model: "voigt", species: "H I" },
];

export function RecipeEditor({ initial, onSaved }: RecipeEditorProps) {
  const [kind, setKind] = useState<RecipeKind>(
    (initial?.recipe_kind as RecipeKind) || "peak_list",
  );
  const [name, setName] = useState<string>(initial?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  // Peak-list state
  const [peaks, setPeaks] = useState<(PeakListEntry & { _row: string })[]>(
    initial?.peak_list?.peaks?.map((p) => ({ _row: rowId(), ...p })) ?? DEFAULT_PEAK_ROWS,
  );
  const [defaultHalfWidth, setDefaultHalfWidth] = useState<number>(
    initial?.peak_list?.default_half_width_nm ?? 0.5,
  );

  // Molecular state
  const [species, setSpecies] = useState<string>(
    initial?.molecular?.species_id ?? "OH_AX",
  );
  const [initialTrot, setInitialTrot] = useState<number>(initial?.molecular?.initial_trot_K ?? 1500);
  const [initialTvib, setInitialTvib] = useState<number>(initial?.molecular?.initial_tvib_K ?? 2500);
  const [instFwhm, setInstFwhm] = useState<number>(initial?.molecular?.instrument_fwhm_nm ?? 0.15);
  const [fitTvib, setFitTvib] = useState<boolean>(initial?.molecular?.fit_tvib ?? false);
  const [instProfile, setInstProfile] = useState<"gaussian" | "voigt">(
    initial?.molecular?.instrument_profile ?? "gaussian",
  );
  const [instLorentz, setInstLorentz] = useState<number>(
    initial?.molecular?.instrument_lorentz_fwhm_nm ?? 0.0,
  );
  const [multiRestart, setMultiRestart] = useState<boolean>(
    !!initial?.molecular?.multi_restart_trot_K,
  );
  const [molWindowMin, setMolWindowMin] = useState<string>(
    initial?.molecular?.window_nm?.[0]?.toString() ?? "",
  );
  const [molWindowMax, setMolWindowMax] = useState<string>(
    initial?.molecular?.window_nm?.[1]?.toString() ?? "",
  );

  // Electron density state
  const [tgK, setTgK] = useState<number>(initial?.electron_density?.Tg_K ?? 650);
  const [edInstGauss, setEdInstGauss] = useState<number>(
    initial?.electron_density?.instrument_gauss_fwhm_nm ?? 0.13,
  );
  const [edLine, setEdLine] = useState<"halpha" | "hbeta">(
    initial?.electron_density?.line ?? "halpha",
  );
  const [edModel, setEdModel] = useState<"single_voigt" | "two_voigt">(
    initial?.electron_density?.model ?? "single_voigt",
  );
  const [edThreshold, setEdThreshold] = useState<number>(
    initial?.electron_density?.intensity_threshold_rel ?? 0.05,
  );

  // Species options
  const [speciesOptions, setSpeciesOptions] = useState<MolecularDatabaseEntry[]>([]);
  useEffect(() => {
    listMolecularDatabases()
      .then((response) => setSpeciesOptions(response.species))
      .catch(() => setSpeciesOptions([]));
  }, []);

  const recipe = useMemo<Recipe>(() => {
    const base: Recipe = {
      id: initial?.id,
      name: name || `${KIND_LABELS[kind]} recipe`,
      diagnostic: kind,
      recipe_kind: kind,
      preprocessing: initial?.preprocessing ?? [],
    };
    if (kind === "peak_list") {
      base.peak_list = {
        peaks: peaks.map(({ _row, ...rest }) => rest),
        default_half_width_nm: defaultHalfWidth,
      };
    } else if (kind === "molecular_v2") {
      const win =
        molWindowMin && molWindowMax
          ? ([Number(molWindowMin), Number(molWindowMax)] as [number, number])
          : null;
      base.molecular = {
        species_id: species as RecipeMolecularSpeciesId,
        window_nm: win,
        initial_trot_K: initialTrot,
        initial_tvib_K: fitTvib ? initialTvib : null,
        instrument_fwhm_nm: instFwhm,
        fit_tvib: fitTvib,
        instrument_profile: instProfile,
        instrument_lorentz_fwhm_nm: instProfile === "voigt" ? instLorentz : 0,
        fit_instrument_lorentz: instProfile === "voigt",
        multi_restart_trot_K: multiRestart ? [500, 1500, 3500] : null,
      };
    } else if (kind === "electron_density") {
      base.electron_density = {
        Tg_K: tgK,
        instrument_gauss_fwhm_nm: edInstGauss,
        line: edLine,
        model: edModel,
        intensity_threshold_rel: edThreshold,
      };
    }
    return base;
  }, [
    initial,
    kind,
    name,
    peaks,
    defaultHalfWidth,
    species,
    initialTrot,
    initialTvib,
    instFwhm,
    fitTvib,
    instProfile,
    instLorentz,
    multiRestart,
    molWindowMin,
    molWindowMax,
    tgK,
    edInstGauss,
    edLine,
    edModel,
    edThreshold,
  ]);

  async function persist() {
    setBusy(true);
    setError(null);
    setSavedMessage(null);
    try {
      const saved = await saveRecipe(recipe);
      setSavedMessage(`Saved "${saved.name}"`);
      toast.success("Recipe saved", saved.name);
      onSaved?.(saved);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Save failed";
      setError(message);
      toast.error("Recipe save failed", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Recipe Editor</h2>
      </div>

      <div className="grid gap-3">
        <label className="grid gap-1">
          <span className="control-label">Recipe name</span>
          <input
            className="field"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Ar excitation peak areas"
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Recipe kind</span>
          <select
            className="field"
            value={kind}
            onChange={(event) => setKind(event.target.value as RecipeKind)}
          >
            {(Object.keys(KIND_LABELS) as RecipeKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </label>

        {kind === "peak_list" ? (
          <PeakListEditor
            peaks={peaks}
            setPeaks={setPeaks}
            defaultHalfWidth={defaultHalfWidth}
            setDefaultHalfWidth={setDefaultHalfWidth}
          />
        ) : null}

        {kind === "molecular_v2" ? (
          <MolecularEditor
            speciesOptions={speciesOptions}
            species={species}
            setSpecies={setSpecies}
            molWindowMin={molWindowMin}
            setMolWindowMin={setMolWindowMin}
            molWindowMax={molWindowMax}
            setMolWindowMax={setMolWindowMax}
            initialTrot={initialTrot}
            setInitialTrot={setInitialTrot}
            initialTvib={initialTvib}
            setInitialTvib={setInitialTvib}
            instFwhm={instFwhm}
            setInstFwhm={setInstFwhm}
            fitTvib={fitTvib}
            setFitTvib={setFitTvib}
            instProfile={instProfile}
            setInstProfile={setInstProfile}
            instLorentz={instLorentz}
            setInstLorentz={setInstLorentz}
            multiRestart={multiRestart}
            setMultiRestart={setMultiRestart}
          />
        ) : null}

        {kind === "electron_density" ? (
          <ElectronDensityEditor
            tgK={tgK}
            setTgK={setTgK}
            edInstGauss={edInstGauss}
            setEdInstGauss={setEdInstGauss}
            edLine={edLine}
            setEdLine={setEdLine}
            edModel={edModel}
            setEdModel={setEdModel}
            edThreshold={edThreshold}
            setEdThreshold={setEdThreshold}
          />
        ) : null}

        {kind !== "peak_list" && kind !== "molecular_v2" && kind !== "electron_density" ? (
          <div className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" style={{ borderRadius: 6 }}>
            Legacy recipe kind: parameters are not editable here. Edit via the JSON view on the right or use the Analysis panel directly.
          </div>
        ) : null}

        {error ? (
          <div className="border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
            {error}
          </div>
        ) : null}
        {savedMessage ? (
          <div className="border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900" style={{ borderRadius: 6 }}>
            {savedMessage}
          </div>
        ) : null}

        <div>
          <button className="primary-button" onClick={persist} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save recipe
          </button>
        </div>
      </div>
    </section>
  );
}

type RecipeMolecularSpeciesId = "OH_AX" | "N2_CB" | "N2plus_BX" | "NH_AX" | "NO_BX";

function PeakListEditor({
  peaks,
  setPeaks,
  defaultHalfWidth,
  setDefaultHalfWidth,
}: {
  peaks: (PeakListEntry & { _row: string })[];
  setPeaks: React.Dispatch<React.SetStateAction<(PeakListEntry & { _row: string })[]>>;
  defaultHalfWidth: number;
  setDefaultHalfWidth: (n: number) => void;
}) {
  function updatePeak(rowKey: string, patch: Partial<PeakListEntry>) {
    setPeaks((current) =>
      current.map((row) => (row._row === rowKey ? { ...row, ...patch } : row)),
    );
  }
  function removePeak(rowKey: string) {
    setPeaks((current) => current.filter((row) => row._row !== rowKey));
  }
  function addRow() {
    setPeaks((current) => [
      ...current,
      { _row: rowId(), label: "", center_nm: 0, half_width_nm: defaultHalfWidth, fit_model: null },
    ]);
  }

  return (
    <div className="grid gap-2">
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-1">
          <span className="control-label">Default half-width (nm)</span>
          <input
            className="field"
            type="number"
            step="0.05"
            value={defaultHalfWidth}
            onChange={(event) => setDefaultHalfWidth(Number(event.target.value))}
          />
        </label>
      </div>

      <div className="overflow-hidden border border-line" style={{ borderRadius: 6 }}>
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-normal text-slate-600">
            <tr>
              <th className="border-b border-line px-2 py-1.5">Label</th>
              <th className="border-b border-line px-2 py-1.5">Center nm</th>
              <th className="border-b border-line px-2 py-1.5">+/- nm</th>
              <th className="border-b border-line px-2 py-1.5">Fit</th>
              <th className="border-b border-line px-2 py-1.5">Species</th>
              <th className="border-b border-line px-2 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {peaks.map((peak) => (
              <tr key={peak._row} className="odd:bg-white even:bg-slate-50">
                <td className="border-b border-line px-2 py-1">
                  <input
                    className="field h-7 px-2 text-xs"
                    value={peak.label ?? ""}
                    onChange={(event) => updatePeak(peak._row, { label: event.target.value })}
                  />
                </td>
                <td className="border-b border-line px-2 py-1">
                  <input
                    className="field h-7 w-24 px-2 text-xs"
                    type="number"
                    step="0.001"
                    value={peak.center_nm}
                    onChange={(event) => updatePeak(peak._row, { center_nm: Number(event.target.value) })}
                  />
                </td>
                <td className="border-b border-line px-2 py-1">
                  <input
                    className="field h-7 w-20 px-2 text-xs"
                    type="number"
                    step="0.05"
                    value={peak.half_width_nm ?? defaultHalfWidth}
                    onChange={(event) => updatePeak(peak._row, { half_width_nm: Number(event.target.value) })}
                  />
                </td>
                <td className="border-b border-line px-2 py-1">
                  <select
                    className="field h-7 w-28 px-2 text-xs"
                    value={peak.fit_model ?? ""}
                    onChange={(event) =>
                      updatePeak(peak._row, {
                        fit_model: (event.target.value || null) as PeakListEntry["fit_model"],
                      })
                    }
                  >
                    <option value="">none</option>
                    <option value="gaussian">gaussian</option>
                    <option value="lorentzian">lorentzian</option>
                    <option value="voigt">voigt</option>
                  </select>
                </td>
                <td className="border-b border-line px-2 py-1">
                  <input
                    className="field h-7 w-20 px-2 text-xs"
                    value={peak.species ?? ""}
                    onChange={(event) => updatePeak(peak._row, { species: event.target.value })}
                  />
                </td>
                <td className="border-b border-line px-2 py-1 text-right">
                  <button
                    className="icon-button h-7 w-7"
                    onClick={() => removePeak(peak._row)}
                    title="Remove peak"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
            {peaks.length === 0 ? (
              <tr>
                <td className="px-3 py-3 text-center text-slate-500" colSpan={6}>
                  No peaks yet
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <button className="text-button w-fit" onClick={addRow}>
        <Plus className="h-4 w-4" />
        Add peak
      </button>
    </div>
  );
}

function MolecularEditor(props: {
  speciesOptions: MolecularDatabaseEntry[];
  species: string;
  setSpecies: (s: string) => void;
  molWindowMin: string;
  setMolWindowMin: (s: string) => void;
  molWindowMax: string;
  setMolWindowMax: (s: string) => void;
  initialTrot: number;
  setInitialTrot: (n: number) => void;
  initialTvib: number;
  setInitialTvib: (n: number) => void;
  instFwhm: number;
  setInstFwhm: (n: number) => void;
  fitTvib: boolean;
  setFitTvib: (b: boolean) => void;
  instProfile: "gaussian" | "voigt";
  setInstProfile: (p: "gaussian" | "voigt") => void;
  instLorentz: number;
  setInstLorentz: (n: number) => void;
  multiRestart: boolean;
  setMultiRestart: (b: boolean) => void;
}) {
  return (
    <div className="grid gap-2">
      <label className="grid gap-1">
        <span className="control-label">Species</span>
        <select className="field" value={props.species} onChange={(e) => props.setSpecies(e.target.value)}>
          {props.speciesOptions.length === 0
            ? ["OH_AX", "N2_CB", "N2plus_BX", "NH_AX", "NO_BX"].map((id) => (
                <option key={id} value={id}>{id}</option>
              ))
            : props.speciesOptions.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} — {entry.line_count.toLocaleString()} lines
                  {entry.available ? "" : " (unavailable)"}
                </option>
              ))}
        </select>
      </label>
      <div className="grid grid-cols-4 gap-2">
        <label className="grid gap-1">
          <span className="control-label">Window min nm</span>
          <input
            className="field"
            type="number"
            step="0.1"
            placeholder="default"
            value={props.molWindowMin}
            onChange={(e) => props.setMolWindowMin(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Window max nm</span>
          <input
            className="field"
            type="number"
            step="0.1"
            placeholder="default"
            value={props.molWindowMax}
            onChange={(e) => props.setMolWindowMax(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Initial Trot (K)</span>
          <input
            className="field"
            type="number"
            value={props.initialTrot}
            onChange={(e) => props.setInitialTrot(Number(e.target.value))}
          />
        </label>
        <label className="grid gap-1">
          <span className="control-label">Inst Gauss FWHM nm</span>
          <input
            className="field"
            type="number"
            step="0.01"
            value={props.instFwhm}
            onChange={(e) => props.setInstFwhm(Number(e.target.value))}
          />
        </label>
      </div>

      <label className="flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm" style={{ borderRadius: 6 }}>
        <span>Fit Tvib separately</span>
        <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={props.fitTvib} onChange={(e) => props.setFitTvib(e.target.checked)} />
      </label>
      {props.fitTvib ? (
        <label className="grid gap-1">
          <span className="control-label">Initial Tvib (K)</span>
          <input className="field" type="number" value={props.initialTvib} onChange={(e) => props.setInitialTvib(Number(e.target.value))} />
        </label>
      ) : null}

      <label className="grid gap-1">
        <span className="control-label">Instrument profile</span>
        <select className="field" value={props.instProfile} onChange={(e) => props.setInstProfile(e.target.value as "gaussian" | "voigt")}>
          <option value="gaussian">Gaussian</option>
          <option value="voigt">Voigt (Gauss + Lorentz)</option>
        </select>
      </label>
      {props.instProfile === "voigt" ? (
        <label className="grid gap-1">
          <span className="control-label">Inst Lorentz FWHM nm (initial)</span>
          <input className="field" type="number" step="0.01" value={props.instLorentz} onChange={(e) => props.setInstLorentz(Number(e.target.value))} />
        </label>
      ) : null}

      <label className="flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm" style={{ borderRadius: 6 }}>
        <span>Multi-restart [500, 1500, 3500] K</span>
        <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={props.multiRestart} onChange={(e) => props.setMultiRestart(e.target.checked)} />
      </label>
    </div>
  );
}

function ElectronDensityEditor(props: {
  tgK: number;
  setTgK: (n: number) => void;
  edInstGauss: number;
  setEdInstGauss: (n: number) => void;
  edLine: "halpha" | "hbeta";
  setEdLine: (l: "halpha" | "hbeta") => void;
  edModel: "single_voigt" | "two_voigt";
  setEdModel: (m: "single_voigt" | "two_voigt") => void;
  edThreshold: number;
  setEdThreshold: (n: number) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
      <label className="grid gap-1">
        <span className="control-label">Tg (K)</span>
        <input className="field" type="number" step="10" value={props.tgK} onChange={(e) => props.setTgK(Number(e.target.value))} />
      </label>
      <label className="grid gap-1">
        <span className="control-label">Instr Gauss FWHM (nm)</span>
        <input className="field" type="number" step="0.01" value={props.edInstGauss} onChange={(e) => props.setEdInstGauss(Number(e.target.value))} />
      </label>
      <label className="grid gap-1">
        <span className="control-label">Threshold (% of peak)</span>
        <input className="field" type="number" step="0.01" value={props.edThreshold} onChange={(e) => props.setEdThreshold(Number(e.target.value))} />
      </label>
      <label className="grid gap-1">
        <span className="control-label">Line</span>
        <select className="field" value={props.edLine} onChange={(e) => props.setEdLine(e.target.value as "halpha" | "hbeta")}>
          <option value="halpha">H-α (lab Gigosos C=1.78)</option>
          <option value="hbeta">H-β (Gigosos C=4.84; not lab-validated)</option>
        </select>
      </label>
      <label className="grid gap-1">
        <span className="control-label">Model</span>
        <select className="field" value={props.edModel} onChange={(e) => props.setEdModel(e.target.value as "single_voigt" | "two_voigt")}>
          <option value="single_voigt">Single Voigt</option>
          <option value="two_voigt">Two Voigt (two populations)</option>
        </select>
      </label>
    </div>
  );
}
