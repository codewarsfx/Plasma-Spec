export type Metadata = Record<string, string | number | boolean | null | undefined>;

export type PreprocessingOperation = {
  operation: string;
  params: Record<string, unknown>;
};

export type SpectrumSummary = {
  id: string;
  filename: string;
  metadata: Metadata;
  preprocessing_history: PreprocessingOperation[];
  points?: number | null;
  wavelength_min_nm?: number | null;
  wavelength_max_nm?: number | null;
  created_at?: string | null;
};

export type Spectrum = SpectrumSummary & {
  wavelength_nm: number[];
  intensity: number[];
};

export type CurvePoint = {
  wavelength_nm: number;
  value: number;
};

export type FitResult = {
  spectrum_id?: string;
  filename?: string;
  diagnostic: string;
  model?: string;
  species?: string;
  window_nm?: [number, number];
  database_kind?: "demo" | "validated" | string;
  database_source?: string;
  transition_count?: number;
  instrument_profile?: "gaussian" | "voigt" | string;
  fit_tvib?: boolean;
  parameters: Record<string, unknown>;
  parameter_stderr?: Record<string, unknown>;
  instrument_widths_nm?: Record<string, unknown>;
  restart_log?: Array<Record<string, unknown>>;
  n_restarts?: number;
  state_count?: number;
  state_populations?: Array<Record<string, unknown>>;
  boltzmann_by_v?: Array<Record<string, unknown>>;
  solver?: Record<string, unknown>;
  electron_density?: Record<string, unknown>;
  metrics: Record<string, number>;
  fit_quality: "good" | "warning" | "bad" | string;
  warnings: string[];
  analysis_notes?: string[];
  metadata?: Metadata;
  preprocessing_history?: PreprocessingOperation[];
  measured_curve?: CurvePoint[];
  fit_curve?: CurvePoint[];
  residual_curve?: CurvePoint[];
  baseline_curve?: CurvePoint[];
  detected_peaks?: Array<Record<string, unknown>>;
  timestamp?: string;
};

export type RecipeKind =
  | "peak_list"
  | "molecular_v2"
  | "electron_density"
  | "hbeta_voigt"
  | "peak_area"
  | "oh_ax"
  | "n2_cb"
  | "line_identification";

export type RecipePeakListParams = {
  peaks: PeakListEntry[];
  default_half_width_nm?: number;
  default_fit_model?: "gaussian" | "lorentzian" | "voigt" | null;
};

export type RecipeMolecularParams = {
  species_id: "OH_AX" | "N2_CB" | "N2plus_BX" | "NH_AX" | "NO_BX";
  fit_mode?: "boltzmann" | "state_by_state";
  window_nm?: [number, number] | null;
  initial_trot_K?: number;
  initial_tvib_K?: number | null;
  trot_bounds_K?: [number, number];
  tvib_bounds_K?: [number, number];
  instrument_fwhm_nm?: number;
  wavelength_shift_nm?: number;
  fit_tvib?: boolean;
  instrument_profile?: "gaussian" | "voigt";
  instrument_lorentz_fwhm_nm?: number;
  fit_instrument_lorentz?: boolean;
  multi_restart_trot_K?: number[] | null;
  database_source?: "auto" | "sqlite" | "demo";
  max_states?: number;
  min_state_relative_strength?: number;
  fit_wavelength_shift?: boolean;
  fit_instrument_fwhm?: boolean;
};

export type RecipeElectronDensityParams = {
  Tg_K: number;
  instrument_gauss_fwhm_nm?: number;
  line?: "halpha" | "hbeta";
  model?: "single_voigt" | "two_voigt";
  window_nm?: [number, number] | null;
  intensity_threshold_rel?: number;
};

export type Recipe = {
  id?: string;
  name: string;
  diagnostic: string;
  recipe_kind?: RecipeKind;
  window_nm?: [number, number] | null;
  preprocessing: PreprocessingOperation[];
  fit_model?: string;
  fit_parameters?: Record<string, unknown>;
  exports?: string[];
  peak_name?: string;
  peak_list?: RecipePeakListParams;
  molecular?: RecipeMolecularParams;
  electron_density?: RecipeElectronDensityParams;
};

export type PeakListEntry = {
  label?: string | null;
  center_nm: number;
  half_width_nm?: number | null;
  fit_model?: "gaussian" | "lorentzian" | "voigt" | null;
  species?: string | null;
  transition?: string | null;
  notes?: string | null;
};

export type PeakListSingleResult = {
  label: string;
  requested_center_nm: number;
  search_half_width_nm: number;
  window_nm: [number, number];
  fit_model: "gaussian" | "lorentzian" | "voigt" | null;
  data:
    | {
        peak_wavelength_nm: number;
        peak_height_raw: number;
        peak_height_baseline_subtracted: number;
        integrated_area: number;
        baseline_subtracted_area: number;
        fwhm_data_nm: number | null;
        snr: number;
        n_points: number;
        local_baseline_left: number;
        local_baseline_right: number;
      }
    | null;
  fit: Record<string, unknown> | null;
  fit_quality: "good" | "warning" | "bad" | string;
  warnings: string[];
  species?: string | null;
  transition?: string | null;
};

export type PeakListResult = {
  spectrum_id?: string;
  filename?: string;
  metadata?: Metadata;
  diagnostic: "peak_list";
  results: PeakListSingleResult[];
};

export type AtomicLine = {
  species: string;
  wavelength_air_nm: number;
  A_ki_s_1?: number | null;
  acc_A?: string | null;
  E_i_cm1?: number | null;
  E_k_cm1?: number | null;
  g_i?: number | null;
  g_k?: number | null;
  lower_term?: string | null;
  upper_term?: string | null;
  transition?: string | null;
  source?: string | null;
  notes?: string | null;
  source_tag?: string;
  boltzmann_ready?: boolean;
  delta_nm?: number;
};

export type AtomicCatalogSummary = {
  line_count: number;
  species_count: number;
  wavelength_min_nm: number | null;
  wavelength_max_nm: number | null;
  has_nist_live_cache?: boolean;
  has_user_overrides?: boolean;
  source_counts?: Record<string, number>;
  nist_live_path?: string;
  sources?: Record<string, unknown>;
};

export type AtomicNistRefreshRequest = {
  species: string[];
  wavelength_min_nm?: number | null;
  wavelength_max_nm?: number | null;
  mode?: "append" | "replace";
  require_transition_probabilities?: boolean;
  max_lines_per_species?: number;
  timeout_s?: number;
};

export type AtomicNistRefreshResponse = {
  status: "ok" | "partial";
  requested_species: string[];
  fetched: Array<{ species: string; line_count: number; url: string; ssl_verified?: boolean }>;
  failures: Array<{ species: string; error: string }>;
  imported_rows: number;
  live_cache: { path: string; line_count: number; species_count: number };
  catalog_summary: AtomicCatalogSummary;
  nist_endpoint: string;
  mode: "append" | "replace";
};

export type AtomicForwardFitRequest = {
  spectrum_id: string;
  species: string[];
  window_nm: [number, number];
  preprocessing?: PreprocessingOperation[];
  initial_temperature_K?: number;
  temperature_bounds_K?: [number, number];
  fit_temperature?: boolean;
  instrument_profile?: "gaussian" | "voigt";
  instrument_fwhm_nm?: number;
  instrument_fwhm_bounds_nm?: [number, number];
  fit_instrument_fwhm?: boolean;
  instrument_lorentz_fwhm_nm?: number;
  instrument_lorentz_fwhm_bounds_nm?: [number, number];
  fit_instrument_lorentz?: boolean;
  wavelength_shift_nm?: number;
  wavelength_shift_bounds_nm?: [number, number];
  fit_wavelength_shift?: boolean;
  species_weights?: Record<string, number>;
  fit_species_scales?: boolean;
  baseline_order?: 0 | 1;
  max_lines?: number;
  top_contributions?: number;
};

export type AtomicLineContribution = {
  species: string;
  wavelength_air_nm: number;
  relative_strength: number;
  A_ki_s_1?: number | null;
  E_k_cm1?: number | null;
  g_k?: number | null;
  transition?: string | null;
  source_tag?: string | null;
  line_ref?: string | null;
};

export type ElectronDensityRequest = {
  spectrum_id: string;
  Tg_K: number;
  instrument_gauss_fwhm_nm?: number;
  line?: "halpha" | "hbeta";
  model?: "single_voigt" | "two_voigt";
  window_nm?: [number, number] | null;
  intensity_threshold_rel?: number;
  center_initial_nm?: number | null;
  lorentz_initial_nm?: number;
  lorentz2_initial_nm?: number;
  weight_initial?: number;
  center_bounds_nm?: [number, number] | null;
  lorentz_bounds_nm?: [number, number];
  Tg_uncertainty_K?: number | null;
  preprocessing?: PreprocessingOperation[];
};

export type ElectronDensityResult = FitResult & {
  line?: "halpha" | "hbeta";
  model?: "single_voigt" | "two_voigt";
  Tg_K?: number;
  Tg_uncertainty_K?: number | null;
  calibration_source?: string;
  calibration_validated?: boolean;
  stark_constant_nm?: number;
  vdw_prefactor_nm?: number;
  vdw_tg_exponent?: number;
  voigt_fit?: Record<string, unknown>;
  fwhm_breakdown_nm?: {
    instrument_gauss_fwhm_nm: number;
    lorentz_fwhm_nm: number | null;
    lorentz1_fwhm_nm: number | null;
    lorentz2_fwhm_nm: number | null;
    vdw_fwhm_nm: number;
    stark_fwhm_nm: number;
    voigt_total_fwhm_nm: number;
  };
  electron_density?: {
    electron_density_cm3: number | null;
    stark_fwhm_nm?: number;
    vdw_fwhm_nm?: number;
    confidence_interval_95?: {
      lower_cm3: number | null;
      upper_cm3: number | null;
      source?: string;
    };
    validated?: boolean;
    source?: string;
    warning?: string | null;
    population_1?: Record<string, unknown>;
    population_2?: Record<string, unknown>;
    weight_pop1?: number;
    weight_pop2?: number;
  };
};

export type MolecularDatabaseEntry = {
  id: string;
  label: string;
  description: string;
  default_window_nm: [number, number];
  typical_trot_K: number;
  notes: string;
  available: boolean;
  database_kind: "validated" | "missing" | "error" | string;
  line_count: number;
  wavelength_min_nm: number | null;
  wavelength_max_nm: number | null;
  path: string | null;
  error?: string;
};

export type BatchRunResult = {
  recipe_name?: string;
  recipe_kind?: RecipeKind;
  completed: number;
  failed: number;
  results: FitResult[];
  rows: Array<Record<string, unknown>>;
  exports?: {
    csv?: { export_id: string; path: string; kind: string };
    xlsx?: { export_id: string; path: string; kind: string };
  };
};
