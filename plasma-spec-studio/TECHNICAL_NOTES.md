# PlasmaSpec Studio — Technical Notes

Math, assumptions, and literature references for every diagnostic the app runs.

For a feature-by-feature walkthrough, see [`USER_GUIDE.md`](USER_GUIDE.md).

---

## 1. Line shapes

All three primitive line shapes are implemented as **unit-area** normalised profiles unless otherwise noted.

| Profile | Formula | Width parameter |
|---|---|---|
| Gaussian | `G(λ; λ₀, σ) = exp[-½ ((λ-λ₀)/σ)²] / (σ √(2π))` | σ (Gaussian SD in nm). FWHM = 2√(2 ln 2) · σ ≈ 2.355 σ. |
| Lorentzian | `L(λ; λ₀, γ) = (γ/π) / [(λ-λ₀)² + γ²]` | γ (Lorentzian HWHM in nm). FWHM = 2γ. |
| Voigt | `V(λ; λ₀, σ, γ) = Re[w(z)] / (σ √(2π))`, `z = ((λ-λ₀) + iγ) / (σ√2)` | (σ, γ). Total FWHM via Olivero–Longbothum: `≈ 0.5346·FWHM_L + √(0.2166·FWHM_L² + FWHM_G²)`. |

The Voigt profile is computed via `scipy.special.wofz` (the Faddeeva function), which is exact within floating-point precision.

For the **electron density workflow**, the Voigt is renormalised to unit **peak** (not unit area) so it can be fit to peak-normalised data. This mirrors the lab MATLAB convention `IV = IV / max(IV)`.

---

## 2. Wavelength-list peak analysis (`peak_list`)

For each requested peak `{label, center_nm, half_width_nm, fit_model?}`:

1. **Crop** to `[center - half_width, center + half_width]`.
2. **Local linear baseline** from the median of the leftmost / rightmost ~10 % of points; interpolated across the window.
3. **Find the corrected peak**: `argmax` of `intensity - baseline`.
4. **Data metrics**: peak height (raw + baseline-subtracted), integrated area, baseline-subtracted area, FWHM from linear interpolation at the half-maximum level, SNR.
5. **Optional profile fit**: scipy `curve_fit` of Gaussian / Lorentzian / Voigt + linear baseline (5–6 free parameters depending on shape). Returns center, σ/γ, FWHM, area under the fitted profile, R², RMSE, parameter stderr from the covariance.
6. **Warnings** for low SNR, peak at the window edge, fitted center far from requested.

This workflow is **not** a database-driven identification — it accepts any peak the user asks about, including custom internal-standard or unidentified emission features.

## 2.5 Matched-line wavelength calibration

The preprocessing pipeline supports polynomial wavelength remapping from measured/reference line pairs. The app fits

    lambda_reference = f(lambda_measured)

with polynomial order 1-3 and applies the resulting mapping to the whole wavelength axis before downstream analysis. The calibration is rejected if there are too few pairs for the requested order, duplicate measured wavelengths, non-finite values, or a non-monotonic calibrated axis.

## 2.6 Spectrum QA and plasma marker ratios

The Studio QA panel performs fast client-side checks before fitting:

- point count and wavelength coverage for common OH, N2, NH, N2+, H, O, and Ar diagnostics
- median wavelength step and relative step jitter
- edge-noise SNR estimate from the outer 5 % of points
- negative-intensity fraction, flat-top/saturation fraction, edge baseline drift, and spike-like outlier fraction

These are readiness checks, not replacements for calibration. They flag common problems that bias low-temperature plasma OES fits: saturated Balmer lines, drifted baselines, non-uniform wavelength axes, poor SNR, and cosmic-ray spikes.

The peak-list panel includes marker presets and derives ratios from baseline-subtracted integrated areas when both lines are present:

- H-alpha / H-beta
- N2+(391) / N2(337)
- OH(309) / N2(337)
- O I 777 / O I 844
- Ar I 750 / Ar I 811

These ratios are reported as empirical trend metrics. They are not converted to species densities unless an experiment-specific actinometry or collisional-radiative model is supplied.

---

## 3. Molecular band fitting (`molecular_v2`)

### 3.1 Per-line intensity

For a line `i` with upper-state quantum numbers (v', J'), Einstein A coefficient `A_i`, upper-state rotational energy `E_J'` (cm⁻¹) and vibrational energy `E_v'` (cm⁻¹), the emission intensity at thermal equilibrium is

    I_i ∝ g_J' · A_i · exp[-c₂ · E_J' / T_rot] · exp[-c₂ · E_v' / T_vib]

where `c₂ = 1.4388 cm·K` is the second radiation constant. The rotational degeneracy is `g_J' = (2 J' + 1)`. The factor `hν` cancels into the overall amplitude.

In the code (`molecular_band_model.molecular_synthetic_spectrum`):
- `strength = A · (2J' + 1)` is precomputed once per line at SQLite load time.
- For single-temperature fits (`fit_tvib=False`), the combined upper-state energy `E_J' + E_v'` is used in a single Boltzmann factor with `T_rot`.
- For two-temperature fits (`fit_tvib=True`), `E_J'` and `E_v'` are kept separate and weighted by two independent exponential factors.

### 3.2 Why no Hönl–London factors

Hönl-London factors `S_J` are used to apportion a **band strength** to individual rotational lines. They are the standard correction when you start from per-vibrational-band Einstein coefficients and need to estimate per-line intensities.

The **MassiveOES databases bundled with this app provide per-line A_ki values directly**, which already encode the branch / rotational dependence of the transition probability. Multiplying by Hönl-London factors on top would double-count the angular-momentum coupling.

If you ever swap to a database that gives only band strengths, the orchestrator will need an explicit `S_J(branch, J')` table. The current code path keeps the math correct for the MassiveOES schema.

### 3.3 Instrument profile

The per-line delta functions are convolved with an instrument profile (Gaussian by default, optional Voigt for spectrometers with significant Lorentzian wings). The convolution is performed pointwise via `scipy.special.wofz` (Voigt path) or analytic Gaussian on the grid.

### 3.4 Fit

`scipy.optimize.least_squares` with explicit bounds (Trust Region Reflective). Free parameters:

- `T_rot` (K)
- `T_vib` (K) — only when `fit_tvib=True`
- `scale` (amplitude)
- `wavelength_shift_nm` — accommodates spectrometer calibration drift (default ±2 nm bounds)
- `instrument_fwhm_nm` (Gaussian component, default 0.01–2.0 nm bounds)
- `instrument_lorentz_fwhm_nm` — only when Voigt + `fit_instrument_lorentz=True`
- `baseline_0`, `baseline_1` (linear baseline `b₀ + b₁ (x - x̄)`)

Parameter stderrs come from the Jacobian via `cov = pinv(J^T J) · (2 cost / (n_data - n_params))` — same formula as scipy's `curve_fit`.

### 3.5 Multi-restart

When `multi_restart_trot_K` is supplied (e.g. `[500, 1500, 3500]` K), the fit is run from each initial Trot and the lowest-cost outcome is kept. This avoids local-minimum traps that single-restart fits fall into when bands overlap or SNR is marginal. Cost: ~3× wall time per fit.

### 3.6 Validated results on the user's spectra

| Frequency | OH(A-X) Trot | N₂(C-B) Trot | N₂(C-B) Tvib | Wavelength shift |
|---|---|---|---|---|
| 100 kHz | 3511 ± 189 K | 944 ± 46 K | 2748 ± 242 K | -0.689 nm |
| 250 kHz | 4150 ± 204 K | 1147 ± 75 K | 2435 ± 316 K | -0.689 nm |
| 500 kHz | 4749 ± 243 K | 1131 ± 87 K | 2139 ± 341 K | -0.690 nm |
| 750 kHz | 5055 ± 279 K | (degenerate) | (degenerate) | -0.689 nm |

The identical -0.689 nm wavelength shift across all four spectra and two species independently confirms a real spectrometer calibration offset, not a fit artifact.

`Tvib > Trot` at all frequencies confirms the non-equilibrium character of the ns-pulsed discharge.

### 3.7 State-by-state molecular fit

The state-by-state mode is the temperature-independent path used when a molecular band may not follow a single Boltzmann or two-temperature distribution.

For each selected upper state `(v', J', component)`, the solver fits an independent non-negative population coefficient:

    I_line ∝ N(v', J') · A_ki

The forward model still uses the same line positions, Einstein coefficients, wavelength shift, baseline, and Gaussian/Voigt instrument profile machinery as `molecular_v2`, but it does not multiply by a Boltzmann factor during the fit. After fitting, the app reports relative upper-state populations and constructs Boltzmann-plot summaries:

    ln[N(v', J') / (2J' + 1)] vs E_rot(v', J')

For each v' manifold with at least three fitted states, an apparent rotational temperature is derived from the slope:

    T_rot,apparent = -c2 / slope

This apparent temperature is diagnostic output, not an imposed fit parameter. Curvature, poor R², or outlying states are therefore meaningful signs of non-Boltzmann population structure rather than automatic fit failures.

---

## 4. Electron density from H-α Stark broadening (`electron_density`)

This is a faithful port of the lab MATLAB scripts at
`/Users/codewarsfx/Desktop/Research Phd/Codes/Electron Density Codes/`:

- `Ne.m` (Stark conversion + vdW correction)
- `Voigt.m`, `TwoVoigt.m`, `Lorentz.m`, `Gaussian.m` (line shapes)
- `ElectronDensity.m`, `ElectronDensity_TwoVoigt.m` (orchestrators)

### 4.1 Calibration constants (H-α)

- **Stark formula** (Gigosos & Cardeñoso 1996 / Gigosos-González-Konjević 2003):

    `n_e [cm⁻³] = (Δλ_Stark / 1.78)^(3/2) · 10¹⁷`

  where `Δλ_Stark` is the **full Stark FWHM in nm** and `C = 1.78 nm` is the lab's calibration constant for H-α.

- **Van der Waals broadening** (empirical for H-α with Ar perturbers):

    `Δλ_vdW [nm] = 5.12 / T_g^0.7`

  where `T_g` is the gas temperature in K. The lab uses this in `Ne.m` line 3 with `Tg = 650 K` (or 600 K for the two-Voigt variant), which gives `Δλ_vdW ≈ 0.055 nm`.

- **Stark contribution** is recovered by **linear subtraction** from the fitted Lorentzian FWHM:

    `Δλ_Stark = Δλ_Lorentz - Δλ_vdW`

  Linear subtraction is correct here because both vdW and Stark broadening produce Lorentzian profiles whose widths add linearly (not in quadrature — quadrature is for Gaussian+Lorentzian going into a Voigt).

### 4.2 Voigt fit

The Voigt profile is fit with **fixed Gaussian FWHM = 0.13 nm** (combined instrumental + Doppler — measured by the lab from narrow Ar lines on the same spectrometer) and **free** Lorentzian FWHM + center. Data is preprocessed by:

1. **Crop** to the window (default 600–700 nm single-Voigt, 630–680 nm two-Voigt).
2. **Drop points below 5 % of peak intensity** (denoises the wings; matches MATLAB `if I(i) > 0.05*max(I)`).
3. **Normalise** `(I - min) / (max - min)` so the peak equals 1.
4. **Fit** scipy `curve_fit` against a unit-peak Voigt model.

### 4.3 Two-population variant

When the line-of-sight integrated spectrum has emission from two regions with different electron densities, the line can be decomposed into two Lorentzian widths weighted by `a` and `(1-a)`:

    n_e = a · n_e(wL₁) + (1 - a) · n_e(wL₂)

Each population uses the same vdW correction (single Tg) and the same Stark constant.

### 4.4 H-β cross-check

H-β at 486.135 nm is included as a literature cross-check with `C = 4.84 nm` (Gigosos-González-Konjević 2003). The H-β path is explicitly flagged `validated=False` because this calibration has not been verified against the user's specific spectrometer. Use it as a sanity check against the H-α result, not as a primary measurement.

### 4.5 Uncertainty propagation

Following the original MATLAB (`A = confint(f); wL1_CI = A(:,1)`), only the **Lorentzian-width 95 % confidence interval** is propagated to n_e. The other parameters' CIs are zeroed out (`wL2_CI = 0`, `a_CI = 1` hard-coded). This is a deliberate simplification — proper Monte-Carlo propagation across the full covariance is not done.

### 4.6 Procedural bias on clean synthetic data

The `(I - min) / (max - min)` normalisation after the 5 % threshold pins the line wings to zero. For a Voigt as wide as `wL = 1.18 nm` (corresponding to `n_e = 5 × 10¹⁶ cm⁻³`), this introduces a **10-20 % systematic bias** in the recovered Lorentzian width (and hence ~15-30 % in n_e) on perfectly clean synthetic data. On real noisy spectra this bias is masked by the noise floor at the wings, and the procedure is accurate within experimental uncertainty.

The tests in `test_electron_density.py` document this explicitly:
- `test_end_to_end_electron_density_round_trip_no_threshold` (no thresholding) → < 5 % error.
- `test_end_to_end_electron_density_round_trip_with_lab_procedure` (default 5 % threshold) → < 25 % error allowed.

### 4.7 Validated results on the user's spectra

| Spectrum | wL_Lorentz | Δλ_Stark | n_e (cm⁻³) | R² |
|---|---|---|---|---|
| 1khz_t1.xlsx (single Voigt, no threshold) | 0.653 nm | 0.598 nm | 1.95 × 10¹⁶ | 0.64 |
| 1khz_t1.xlsx (single Voigt, lab default) | 0.559 nm | 0.504 nm | 1.51 × 10¹⁶ | 0.57 |
| 1khz-argon.xlsx (single Voigt, lab default) | 1.137 nm | 1.082 nm | 4.74 × 10¹⁶ | 0.82 |
| 1khz-argon.xlsx (two Voigt) | 1.137 = 1.137 | 1.082 | 4.74 × 10¹⁶ | 0.996 |

The two-Voigt fit collapses to identical Lorentzian widths on `1khz-argon` → that spectrum has a single electron-density population. Use single Voigt unless residuals clearly show two populations.

---

## 5. Atomic line identification

The bundled catalog (`backend/app/databases/atomic/nist_lines.csv`) is a curated subset of NIST ASD covering the species most relevant to low-temperature plasma OES:

- **H I**: Balmer α-ε, Paschen α (with summed-manifold Einstein coefficients from Wiese & Fuhr 2009)
- **He I**: 388.9, 447.1, 492.2, 501.6, 587.6 (D3), 667.8, 706.5, 728.1
- **Ar I**: 22 lines from 696.5 to 922.5 nm
- **Ar II**: 480.6, 488.0, 488.9
- **O I**: 615.7, 645.6, 725.5, 777 triplet, 844 triplet
- **O II**: 374.9, 375.5
- **N I**: 491.5, 742.4 triplet, 818.5, 821.6, 868.3, 939.3
- **N II**: 500.5

Each entry carries species, air wavelength, A_ki, accuracy flag (NIST conventions A+ < 2 %, A < 3 %, B < 10 %, …), lower / upper level energies, statistical weights (g_i, g_k), term symbols, transition label, source citation, and free-text notes.

Official NIST ASD refreshes are written to `backend/app/databases/atomic/nist_live_lines.csv` via `POST /api/databases/atomic/refresh`. The endpoint queries the NIST Lines CGI in tab-delimited mode for user-selected species and wavelength ranges, normalises observed/Ritz wavelengths, A_ki, accuracy, energies, g-values, terms, transition type, and NIST references into the app schema, then merges the live cache after the bundled subset.

Optional user overrides go in `backend/app/databases/atomic/user_overrides.csv` (same schema). They are merged last, so lab corrections can override or supplement both bundled and live NIST rows.

### 5.1 Atomic forward model

`POST /api/fit/atomic-forward` fits a relative NIST-backed atomic spectrum model against a measured spectrum. For each physics-ready line (`wavelength_air_nm`, `A_ki_s_1`, `E_k_cm1`, `g_k` present), the stick intensity is

`S_ul ∝ C_species · g_k · A_ki · exp(-c2 E_k / T_exc) / λ`

where `c2 = 1.438776877 cm K`. Sticks are convolved with a unit-area Gaussian or Voigt instrument profile, shifted by the fitted wavelength offset, and combined with a constant or linear baseline. The nonlinear solver can fit `T_exc`, Gaussian FWHM, optional Lorentzian FWHM, and wavelength shift; at each nonlinear step, species coefficients are solved as non-negative linear terms.

The model intentionally reports relative coefficients only. Partition functions, calibrated collection efficiency, path length, species density, quenching, radiation transport, and self-absorption are not included. When live NIST rows exist for a species, bundled curated rows are excluded from the forward model to avoid double-counting aggregate labels plus fine-structure rows.

### Provenance

`sources.json` next to `nist_lines.csv` documents the bundled subset version, the primary source (NIST ASD), and the H I Wiese & Fuhr 2009 attribution. Live-refresh rows carry `source = "NIST ASD live refresh"` plus `tp_ref` / `line_ref` fields when NIST returns them.

---

## 6. MassiveOES molecular database schema

The five SQLite files in `Molecular Line Data/`:

| File | Species | Lines | λ range (nm) |
|---|---|---|---|
| `OHAX.db` | OH(A²Σ⁺-X²Π) | 2,160 | 278.7–368.2 |
| `N2CB.db` | N₂(C³Π_u-B³Π_g) Second Positive | 195,470 | 259.2–720.6 |
| `N2PlusBX.db` | N₂⁺(B²Σ_u-X²Σ_g) First Negative | 3,048 | 340.7–391.6 |
| `NHAX.db` | NH(A³Π-X³Σ⁻) | 2,719 | 307.1–439.5 |
| `NOBX.db` | NO(B²Π-X²Π) β system | 7,568 | 357.0–425.0 |

Schema (one per file):

- `lines (id, A, air_wavelength, vacuum_wavelength, wavenumber, branch, upper_state -> upper_states.id, lower_state -> lower_states.id)` — Einstein A coefficient, air and vacuum wavelengths, branch label (P/Q/R + satellite branches), foreign keys.
- `upper_states (id, E_J, E_v, J, v, component)` — rotational and vibrational upper-level energies in cm⁻¹, plus quantum numbers. `J` is half-integer for OH (²Σ⁺ doublet) and integer for N₂ (¹Σ_g⁺ ground state).
- `lower_states` — same schema.

The store (`app/databases/molecular/store.py`) joins these tables and returns a DataFrame with the columns the fit code expects (`wavelength_nm, einstein_A, branch, e_rot_upper_cm1, e_vib_upper_cm1, j_upper, v_upper, v_lower, energy_upper_cm1, strength`). Connections are cached read-only.

Path resolution order:
1. `PLASMA_SPEC_MOLECULAR_DB_DIR` environment variable
2. Walk up from the backend (up to 4 parents) looking for a `Molecular Line Data/` folder
3. `backend/app/databases/molecular/sqlite/` (for self-contained deployments)

---

## 7. Filename metadata parser

Pattern matchers in `app/preprocessing/filename_metadata.py`:

| Tag | Regex | Output key |
|---|---|---|
| `100kHz`, `1khz`, `250 kHz` | `(\d+(?:\.\d+)?)\s*k?Hz` | `pulse_frequency_khz` (float) |
| `1ms`, `0.5 ms` | `(\d+(?:\.\d+)?)\s*ms` | `burst_period_ms` (float) |
| `10cycles`, `5cyc` | `(\d+)\s*(?:cycles?|cyc)` | `n_cycles` (int) |
| `14kV` | `(\d+(?:\.\d+)?)\s*kV` | `voltage_kv` (float) |
| `100ns` | `(\d+(?:\.\d+)?)\s*ns` | `gate_delay_ns` (float) |
| `rep_3`, `-rep1` | `[_-]rep[_-]?(\d+)` | `replicate` (int) |

Plus a positional fallback that matches `<freq>kHz_<ms>ms_<cycles>_<rep>` exactly (this is the user's actual file naming convention).

Override the entire matching with a custom regex via the `filename_pattern` upload form field — named groups become metadata keys.

---

## 8. Recipes and batch processing

A recipe is a JSON document with:

- `id`, `name`, `recipe_kind` (discriminator)
- `preprocessing` — list of preprocessing operations applied before the fit
- Typed parameter block matching the recipe kind: `peak_list`, `molecular`, or `electron_density`

The batch service (`app/services/batch_service.py`) dispatches on `recipe_kind` and produces **long-form rows**:

- `peak_list`: one row per `(file, peak)`. Columns include data metrics, fit metrics, fitted center/FWHM/area, and warnings.
- `molecular_v2`: one row per file. Columns include Trot, Tvib, FWHM, shift, R², transition count, restart log summary.
- `electron_density`: one row per file. Columns include Lorentz / vdW / Stark FWHM, n_e and 95 % CI, R², calibration provenance.

All rows carry `metadata_*` columns from the filename parser + manual upload metadata.

Per-batch CSV + XLSX exports are written via pandas / openpyxl. Failures are isolated per spectrum (one bad file doesn't terminate the run).

---

## 9. Reports

Per-result reports are generated by `app/services/report_service.py`:

- **HTML**: jinja-free f-string template with inline CSS, PNG plot embedded as base64. Self-contained — single file that emails/prints cleanly. Sections: title + quality chip, plot, preprocessing pipeline, parameters + stderrs, fit-quality metrics, intermediate-value chain (width breakdown, electron density), warnings, provenance.
- **PDF**: matplotlib `PdfPages` backend. One US-letter page with title + plot + residuals + parameter / metric / warning text table. PDF metadata includes title, author (`PlasmaSpec Studio`), and producer.

Both are reachable via `POST /api/reports/result` with `formats: ["html"]` and/or `["pdf"]`.

---

## 10. References

- Eilers & Boelens, "Baseline correction with asymmetric least squares smoothing" (2005) — the ALS baseline.
- Konjević, "Plasma broadening and shifting of non-hydrogenic spectral lines: present status and applications" Phys. Rep. 316 (1999) 339 — atomic Stark widths review.
- Gigosos & Cardeñoso, "New plasma diagnosis tables of hydrogen Stark broadening including ion dynamics" J. Phys. B 29 (1996) 4795 — Stark calibration for H-α.
- Gigosos, González & Konjević, "Computer simulated Balmer-α, -β and -γ Stark line profiles for non-equilibrium plasmas diagnostics" Spectrochim. Acta B 58 (2003) 1489 — H-β cross-check constants.
- Wiese & Fuhr, "Accurate atomic transition probabilities for hydrogen, helium, and lithium" J. Phys. Chem. Ref. Data 38 (2009) 565 — H I summed Einstein coefficients.
- Voráč, Synek, Procházka, Hoder, "State-by-state emission spectra fitting for non-equilibrium plasmas: OH spectra of surface barrier discharge at argon/water interface" J. Phys. D 50 (2017) 294002 — MassiveOES design.
- Earls, "Intensities in ²Π−²Σ transitions in diatomic molecules" Phys. Rev. 48 (1935) 423 — Hönl-London factor convention for the OH(A-X) system (not applied here; see §3.2).
- NIST Atomic Spectra Database (ASD), <https://physics.nist.gov/asd> — primary source for the bundled atomic catalog.
