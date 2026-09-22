"use client";

import { Loader2, Play, Save } from "lucide-react";
import { useMemo, useState } from "react";
import {
  analyzePeak,
  fitHbeta,
  fitMolecular,
  fitMolecularStateByState,
  identifyLines,
  saveRecipe,
} from "@/lib/api";
import type { DiagnosticId } from "./DiagnosticSelector";
import type { FitResult, PreprocessingOperation, Recipe } from "@/lib/types";

type FittingPanelProps = {
  spectrumId?: string;
  diagnostic: DiagnosticId;
  windowNm: [number, number];
  preprocessing: PreprocessingOperation[];
  onResult: (result: FitResult) => void;
};

type InstrumentProfile = "gaussian" | "voigt";
type MolecularSpeciesId = "OH_AX" | "N2_CB" | "N2plus_BX" | "NH_AX" | "NO_BX";
type MolecularFitMode = "boltzmann" | "state_by_state";

export function FittingPanel({
  spectrumId,
  diagnostic,
  windowNm,
  preprocessing,
  onResult,
}: FittingPanelProps) {
  const [model, setModel] = useState<"voigt" | "gaussian" | "lorentzian">("voigt");
  const [peakName, setPeakName] = useState("Hbeta");
  const [initialTrot, setInitialTrot] = useState(1500);
  const [initialTvib, setInitialTvib] = useState(2500);
  const [fitTvib, setFitTvib] = useState(false);
  const [molecularFitMode, setMolecularFitMode] = useState<MolecularFitMode>("boltzmann");
  const [maxStates, setMaxStates] = useState(40);
  const [instrumentFwhm, setInstrumentFwhm] = useState(0.15);
  const [instrumentProfile, setInstrumentProfile] = useState<InstrumentProfile>("gaussian");
  const [instrumentLorentzFwhm, setInstrumentLorentzFwhm] = useState(0.05);
  const [multiRestart, setMultiRestart] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedRecipe, setSavedRecipe] = useState<string | null>(null);

  const molecularSpecies = molecularSpeciesForDiagnostic(diagnostic);
  const isMolecular = molecularSpecies !== null;

  const recipe = useMemo<Recipe>(
    () => {
      const speciesId = molecularSpeciesForDiagnostic(diagnostic);
      if (speciesId) {
        const stateByState = molecularFitMode === "state_by_state";
        return {
          name: recipeName(diagnostic, model, windowNm),
          diagnostic: "molecular_v2",
          recipe_kind: "molecular_v2",
          preprocessing,
          molecular: {
            species_id: speciesId,
            fit_mode: molecularFitMode,
            window_nm: windowNm,
            initial_trot_K: stateByState ? undefined : initialTrot,
            initial_tvib_K: !stateByState && fitTvib ? initialTvib : null,
            trot_bounds_K: molecularTrotBounds(diagnostic),
            instrument_fwhm_nm: instrumentFwhm,
            fit_tvib: !stateByState && fitTvib,
            instrument_profile: instrumentProfile,
            instrument_lorentz_fwhm_nm: instrumentProfile === "voigt" ? instrumentLorentzFwhm : 0,
            fit_instrument_lorentz: !stateByState && instrumentProfile === "voigt",
            multi_restart_trot_K: !stateByState && multiRestart ? [500, 1500, 3500] : null,
            max_states: stateByState ? maxStates : undefined,
            min_state_relative_strength: stateByState ? 0 : undefined,
            fit_wavelength_shift: stateByState ? true : undefined,
            fit_instrument_fwhm: stateByState ? true : undefined,
          },
          exports: ["fit_params", "fit_quality", "plots"],
        };
      }
      return {
        name: recipeName(diagnostic, model, windowNm),
        diagnostic,
        window_nm: windowNm,
        preprocessing,
        fit_model: diagnostic === "hbeta_voigt" ? model : undefined,
        fit_parameters: {
          center_bounds: [485.8, 486.4],
          sigma_bounds: [0.001, 1],
          gamma_bounds: [0.001, 1],
          initial_trot_K: initialTrot,
          instrument_fwhm_nm: instrumentFwhm,
        },
        exports: ["fit_params", "fit_quality", "plots"],
        peak_name: peakName,
      };
    },
    [
      diagnostic,
      fitTvib,
      initialTrot,
      initialTvib,
      instrumentFwhm,
      instrumentLorentzFwhm,
      instrumentProfile,
      maxStates,
      model,
      molecularFitMode,
      multiRestart,
      peakName,
      preprocessing,
      windowNm,
    ],
  );

  async function runFit() {
    if (!spectrumId) return;
    setBusy(true);
    setError(null);
    try {
      const common = {
        spectrum_id: spectrumId,
        window_nm: windowNm,
        preprocessing,
      };
      const molecularExtra = {
        initial_trot_K: initialTrot,
        instrument_fwhm_nm: instrumentFwhm,
        fit_tvib: fitTvib,
        initial_tvib_K: fitTvib ? initialTvib : undefined,
        instrument_profile: instrumentProfile,
        instrument_lorentz_fwhm_nm: instrumentProfile === "voigt" ? instrumentLorentzFwhm : 0.0,
        fit_instrument_lorentz: instrumentProfile === "voigt",
        multi_restart_trot_K: multiRestart ? [500, 1500, 3500] : undefined,
      };
      let result: FitResult;
      if (diagnostic === "hbeta_voigt") {
        result = await fitHbeta({ ...common, model });
      } else if (molecularSpecies) {
        if (molecularFitMode === "state_by_state") {
          result = await fitMolecularStateByState({
            ...common,
            species_id: molecularSpecies,
            instrument_fwhm_nm: instrumentFwhm,
            wavelength_shift_nm: 0,
            instrument_profile: instrumentProfile,
            instrument_lorentz_fwhm_nm: instrumentProfile === "voigt" ? instrumentLorentzFwhm : 0.0,
            max_states: maxStates,
            min_state_relative_strength: 0,
            fit_wavelength_shift: true,
            fit_instrument_fwhm: true,
          });
        } else {
          result = await fitMolecular({
            ...common,
            species_id: molecularSpecies,
            ...molecularExtra,
            trot_bounds_K: molecularTrotBounds(diagnostic),
          });
        }
      } else if (diagnostic === "line_identification") {
        result = await identifyLines({ ...common, threshold_rel: 0.1, tolerance_nm: 0.25 });
      } else {
        result = await analyzePeak({ ...common, name: peakName });
      }
      onResult(result);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Fit failed");
    } finally {
      setBusy(false);
    }
  }

  async function persistRecipe() {
    setError(null);
    try {
      const saved = await saveRecipe(recipe);
      setSavedRecipe(saved.name);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Recipe save failed");
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Fit Controls</h2>
        <span className="text-xs text-slate-500">{windowNm[0]}-{windowNm[1]} nm</span>
      </div>

      <div className="grid gap-3">
        {diagnostic === "hbeta_voigt" ? (
          <label className="grid gap-1">
            <span className="control-label">Line shape</span>
            <select className="field" value={model} onChange={(event) => setModel(event.target.value as typeof model)}>
              <option value="voigt">Voigt</option>
              <option value="gaussian">Gaussian</option>
              <option value="lorentzian">Lorentzian</option>
            </select>
          </label>
        ) : null}

        {diagnostic === "peak_area" ? (
          <label className="grid gap-1">
            <span className="control-label">Peak name</span>
            <input className="field" value={peakName} onChange={(event) => setPeakName(event.target.value)} />
          </label>
        ) : null}

        {isMolecular ? (
          <div className="grid gap-2">
            <label className="grid gap-1">
              <span className="control-label">Molecular model</span>
              <select
                className="field"
                value={molecularFitMode}
                onChange={(event) => setMolecularFitMode(event.target.value as MolecularFitMode)}
              >
                <option value="boltzmann">Boltzmann Trot/Tvib</option>
                <option value="state_by_state">State-by-state populations</option>
              </select>
            </label>

            <div className="grid grid-cols-2 gap-2">
              {molecularFitMode === "boltzmann" ? (
                <label className="grid gap-1">
                  <span className="control-label">Initial Trot K</span>
                  <input
                    className="field"
                    type="number"
                    value={initialTrot}
                    onChange={(event) => setInitialTrot(Number(event.target.value))}
                  />
                </label>
              ) : (
                <label className="grid gap-1">
                  <span className="control-label">Max states</span>
                  <input
                    className="field"
                    type="number"
                    min={1}
                    max={250}
                    value={maxStates}
                    onChange={(event) => setMaxStates(Number(event.target.value))}
                  />
                </label>
              )}
              <label className="grid gap-1">
                <span className="control-label">Instr FWHM (Gauss) nm</span>
                <input
                  className="field"
                  type="number"
                  step="0.01"
                  value={instrumentFwhm}
                  onChange={(event) => setInstrumentFwhm(Number(event.target.value))}
                />
              </label>
            </div>

            {molecularFitMode === "boltzmann" ? (
              <label
                className="flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm studio-hover hover:bg-slate-50"
                style={{ borderRadius: 6 }}
                title="Fit a separate vibrational temperature in addition to Trot. Needs a window spanning at least two v'-band heads for meaningful Tvib (e.g. N2(C-B) 330-385 nm)."
              >
                <span className="flex items-center">
                  Fit Tvib separately
                  <span className="hint-pill" aria-label="Two-temperature fit">?</span>
                </span>
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-teal-700"
                  checked={fitTvib}
                  onChange={(event) => setFitTvib(event.target.checked)}
                />
              </label>
            ) : (
              <p className="border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-950" style={{ borderRadius: 6 }}>
                Fits independent upper-state populations, then derives apparent Boltzmann slopes after the fit.
              </p>
            )}

            {molecularFitMode === "boltzmann" && fitTvib ? (
              <label className="grid gap-1">
                <span className="control-label">Initial Tvib K</span>
                <input
                  className="field"
                  type="number"
                  value={initialTvib}
                  onChange={(event) => setInitialTvib(Number(event.target.value))}
                />
              </label>
            ) : null}

            <label className="grid gap-1">
              <span className="control-label">Instrument profile</span>
              <select
                className="field"
                value={instrumentProfile}
                onChange={(event) => setInstrumentProfile(event.target.value as InstrumentProfile)}
              >
                <option value="gaussian">Gaussian</option>
                <option value="voigt">Voigt (Gauss + Lorentz)</option>
              </select>
            </label>

            {instrumentProfile === "voigt" ? (
              <label className="grid gap-1">
                <span className="control-label">Instr Lorentz FWHM nm (initial)</span>
                <input
                  className="field"
                  type="number"
                  step="0.01"
                  value={instrumentLorentzFwhm}
                  onChange={(event) => setInstrumentLorentzFwhm(Number(event.target.value))}
                />
              </label>
            ) : null}

            {molecularFitMode === "boltzmann" ? (
              <>
                <label
                  className="flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm studio-hover hover:bg-slate-50"
                  style={{ borderRadius: 6 }}
                  title="Re-run the fit from three different initial Trot values (500, 1500, 3500 K) and keep the lowest-residual outcome. Costs ~3x runtime; eliminates local-minimum traps."
                >
                  <span className="flex items-center">
                    Multi-restart [500, 1500, 3500] K
                    <span className="hint-pill" aria-label="Multi-restart fit">?</span>
                  </span>
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-teal-700"
                    checked={multiRestart}
                    onChange={(event) => setMultiRestart(event.target.checked)}
                  />
                </label>
                <p className="text-xs text-slate-500">
                  Multi-restart escapes local minima at the cost of ~3x runtime. Recommend when single-restart fits peg at bounds.
                </p>
              </>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <div className="border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" style={{ borderRadius: 6 }}>
            {error}
          </div>
        ) : null}
        {savedRecipe ? (
          <div className="border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900" style={{ borderRadius: 6 }}>
            Saved {savedRecipe}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button className="primary-button" onClick={runFit} disabled={!spectrumId || busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run
          </button>
          <button className="text-button" onClick={persistRecipe} disabled={!spectrumId}>
            <Save className="h-4 w-4" />
            Recipe
          </button>
        </div>
      </div>
    </section>
  );
}

function recipeName(diagnostic: DiagnosticId, model: string, windowNm: [number, number]) {
  if (diagnostic === "hbeta_voigt") return `Hbeta ${model} ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "oh_ax") return `OH(A-X) ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "n2_cb") return `N2(C-B) ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "n2plus_bx") return `N2+(B-X) ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "nh_ax") return `NH(A-X) ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "no_bx") return `NO(B-X) ${windowNm[0]}-${windowNm[1]} nm`;
  if (diagnostic === "line_identification") return `Line ID ${windowNm[0]}-${windowNm[1]} nm`;
  return `${diagnostic} ${windowNm[0]}-${windowNm[1]} nm`;
}

function molecularSpeciesForDiagnostic(diagnostic: DiagnosticId): MolecularSpeciesId | null {
  if (diagnostic === "oh_ax") return "OH_AX";
  if (diagnostic === "n2_cb") return "N2_CB";
  if (diagnostic === "n2plus_bx") return "N2plus_BX";
  if (diagnostic === "nh_ax") return "NH_AX";
  if (diagnostic === "no_bx") return "NO_BX";
  return null;
}

function molecularTrotBounds(diagnostic: DiagnosticId): [number, number] {
  return diagnostic === "oh_ax" || diagnostic === "nh_ax" ? [250, 6000] : [250, 8000];
}
