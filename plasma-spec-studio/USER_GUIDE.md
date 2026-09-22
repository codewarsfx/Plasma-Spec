# PlasmaSpec Studio — User Guide

This guide walks through every feature of the app, in the order you'd use them in a typical experiment.

For the math, assumptions, and references behind each diagnostic, see [`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md).

---

## 1. Install and run

```bash
# Backend (Python 3.13)
cd plasma-spec-studio/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (Node 20+)
cd plasma-spec-studio/frontend
npm install
npm run dev
```

Then open <http://localhost:3000/studio>.

The Python venv ships its own `pip` symlink that may point at a stale path if the project has been moved. Always install via `.venv/bin/python -m pip install <pkg>`, not `.venv/bin/pip`.

---

## 2. Project layout

- `/` — Project landing page. Links to every tool.
- `/studio` — **Workstation** (the primary workspace). Files sidebar + plot + contextual analysis panel + results table + toolbar.
- `/spectra` — Bulk upload + metadata table + overlay-only view (legacy focused workflow).
- `/batch` — Run a saved recipe across many spectra.
- `/dashboard` — Compare fit outputs against metadata (frequency, cycles, gas, replicate).
- `/recipes` — Save and edit reusable analysis configurations.

The legacy `/analysis` URL redirects to `/studio`.

---

## 3. Spectrum import

The importer handles:

- **CSV, TSV, TXT, ASC, DAT** — text files. Wavelength + intensity columns are auto-detected. Headers tolerated. Header-less numeric pairs work too.
- **XLSX, XLSM** — Excel workbooks. Avantes-style metadata rows at the top (`Filename-->`, `Int.time[ms]-->`, `Wavelength [nm]`, …) are parsed into spectrum metadata. The column containing `Wavelength` is auto-detected; otherwise the first numeric column wins.

### Filename metadata parser

Filenames like `100kHz_1ms_10_1.xlsx` are parsed automatically at upload time into `{pulse_frequency_khz: 100, burst_period_ms: 1.0, n_cycles: 10, replicate: 1}`. Other recognised tags include `_12kV`, `_500ns_`, `rep_3`.

You can override with a custom regex by passing `filename_pattern` as a form field at upload (named groups become metadata keys). Set `parse_filename_metadata=false` to skip auto-parsing entirely.

---

## 4. The Studio workstation

### 4.1 Top toolbar

| Tool | Right-panel content |
|---|---|
| **Files** | help text only — use the sidebar to pick a spectrum |
| **Baseline** | Preprocessing pipeline (crop, ALS baseline, normalize, smooth, spike removal) |
| **Peaks** | Wavelength-list peak analysis + atomic line search |
| **Bands** | Molecular fit controls (species, Tvib, profile, multi-restart) |
| **Density** | Electron density via the lab Stark workflow |
| **Sim** | NIST-backed atomic forward model |
| **Lines** | Standalone atomic line database search |
| **Batch** | Quick links to the Batch + Recipes pages |

Clicking a tool tints the wavelength window highlight on the plot in the tool's color.

### 4.2 Left sidebar

- **Search**: filter by filename or any metadata value.
- **Group-by**: group spectra by pulse frequency, burst period, cycles, gas, date, or replicate. Groups are collapsible.
- Click a spectrum to make it the **primary** (drives the plot + analysis).
- Click the eye icon to toggle a spectrum as an **overlay** (drawn as a dotted line on the plot for comparison).
- **Upload**: file picker accepts CSV / TXT / TSV / ASC / DAT / XLSX / XLSM. Multi-file allowed.

### 4.3 Central plot

Tabs above the plot:
- **Spectrum**: primary + overlays + fit curve overlay (when a fit is active).
- **Baseline preview**: raw vs preprocessed side-by-side (active only after enabling at least one preprocessing step).
- **Residuals**: fit residual curve (active only after a fit).

The cursor readout in the top-right corner shows `λ (nm)`, intensity, and the nearest atomic line within 0.5 nm (queried live from the bundled NIST catalog, debounced).

Drag a horizontal rectangle to set the working wavelength window — the right panel automatically picks it up for the next analysis.

### 4.4 Right panel — Baseline

Toggle any of these preprocessing operations. Each row has a `?` pill with a tooltip explaining the math.

- **Crop to window** — restricts the spectrum to the wavelength window above.
- **ALS baseline** — asymmetric-least-squares baseline (lambda=1e5 smoothness, p=0.01 asymmetry).
- **Max normalize** — peak set to 1.
- **Spike removal** — median-filter outliers > 6 sigma.
- **Savitzky–Golay** — window=9 points, polyorder=2. Avoid before FWHM extraction.

### 4.5 Right panel — Peaks (wavelength-list analysis)

Edit the table of peaks you care about: label, center wavelength, half-width, optional fit model (Gaussian / Lorentzian / Voigt), species tag.

For each peak the app reports:

- **Data**: peak center wavelength (max position), peak height (corrected for local baseline), integrated area, baseline-subtracted area, FWHM (from data, if resolvable), SNR.
- **Fit** (when a model is chosen): fitted center, sigma/gamma, FWHM, area under the fitted profile, R², RMSE.

The accompanying **Line Database** panel queries the bundled NIST-derived catalog. Filter by species, wavelength range, or nearest-to-cursor. Click the `+` button next to a search result to push it into the wavelength-list table.

### 4.6 Right panel — Bands (molecular fit)

Pick a diagnostic (OH(A-X), N₂(C-B), …) and configure:

- **Initial Trot (K)** — starting rotational temperature.
- **Initial Tvib (K)** — only used when *Fit Tvib separately* is on.
- **Instrument Gauss FWHM (nm)** — measured instrumental resolution.
- **Instrument profile** — Gaussian (default) or Voigt (Gauss + Lorentz).
- **Initial Lorentz FWHM (nm)** — used when Voigt is selected.
- **Fit Tvib separately** — adds Tvib as a free parameter. Requires a window spanning at least two v'-band heads to constrain Tvib meaningfully.
- **Multi-restart [500, 1500, 3500] K** — re-runs the fit from three initial Trot values and keeps the lowest-residual one. Costs ~3× runtime; eliminates local-minimum traps.

The fit result reports Trot, Tvib, instrument FWHM, wavelength shift, R², RMSE, parameter stderrs from the Jacobian, and the restart-cost log when multi-restart is on.

### 4.7 Right panel — Density (electron density)

Lab Gigosos workflow ported from your MATLAB scripts.

- **Tg (K)** — gas temperature. Used in the van der Waals correction `Δλ_vdW = 5.12 / Tg^0.7`.
- **Instrument Gaussian FWHM (nm)** — measured + Doppler combined, held fixed during the Voigt fit. Lab default = 0.13 nm.
- **Threshold (% of peak)** — drop points below this fraction of the peak before normalizing. Matches MATLAB `ElectronDensity.m` default 0.05.
- **Model** — single Voigt (one population) or two Voigt (two populations weighted by `a`).
- **Line** — H-α (primary, lab Gigosos C=1.78) or H-β (literature cross-check, C=4.84, not lab-validated).
- **Window min / max** — defaults follow MATLAB (600-700 nm single, 630-680 nm two-Voigt).

The result block shows:

- **n_e** in cm⁻³ with a 95 % confidence interval propagated from the Lorentzian-width stderr (matches MATLAB which only propagates wL1's CI).
- **Width breakdown**: instrument Gaussian FWHM, fitted Lorentzian FWHM, vdW FWHM at Tg, **Stark FWHM**, Voigt total.
- **Calibration provenance**: which formula and C value was used.

### 4.8 Right panel — Sim (atomic forward model)

The Sim tool fits a relative NIST-backed atomic forward model to the selected spectrum.

- **Species** — comma-separated atomic species such as `H I, Ar I, O I, N II`.
- **Initial T_exc K** — starting excitation temperature for the Boltzmann upper-state population model.
- **Profile / Gauss FWHM / Lorentz FWHM** — instrument response used to convolve stick lines.
- **Fit T_exc / width / wavelength shift / species scales** — nonlinear and non-negative linear fit controls.
- **Baseline** — constant or linear baseline included during fitting.
- **Max lines** — strongest physics-ready NIST lines retained for runtime.

The result reports T_exc, R², fitted instrument width, wavelength shift, line counts, relative species scales, warnings, residuals, and the strongest contributing NIST lines. The model is relative and optically thin; it is not absolute SPECAIR-style radiance with transport.

### 4.9 Bottom results table

The latest analysis populates a long-form table at the bottom of the workstation. The table auto-detects the result kind:

- **peak_list** → one row per peak with all data + fit columns.
- **molecular** → one row per fit with Trot / Tvib / shift / FWHM.
- **electron_density** → one row with n_e, all FWHM components, Tg.

Headers: CSV download, HTML report, PDF report.

---

## 5. Recipes

A recipe is a saved analysis configuration that can be re-applied to any spectrum (or batch of spectra).

Open `/recipes` (or click "Recipes" in the top nav). The recipe editor has three kind-specific UIs:

- **Wavelength list** — editable peak table + default half-width + default fit model.
- **Molecular** — species picker (auto-populated from the molecular DB endpoint), window, initial Trot/Tvib, instrument FWHM, fit-Tvib toggle, profile picker, multi-restart toggle.
- **Electron density** — Tg, instrument Gaussian FWHM, line, model, threshold.

Legacy kinds (`hbeta_voigt`, `peak_area`, `oh_ax`, `n2_cb`, `line_identification`) are read-only here; edit them via the legacy `fit_parameters` JSON if needed.

Hit **Save recipe**. Recipes are stored in the same SQLite DB as the spectra.

---

## 6. Batch processing

Open `/batch`. Pick a recipe, select spectra (multi-checkbox), hit **Run Batch**.

The result table is **long-form**:

- For `peak_list` recipes: one row per `(file, peak)`. With 4 peaks × 12 spectra you get 48 rows.
- For `molecular_v2` / `electron_density` recipes: one row per file.

Every row carries `metadata_*` columns (from the filename parser + manual metadata at upload).

Both **CSV** and **XLSX** downloads are generated automatically; download links appear in the header after the batch finishes.

Failures are isolated per spectrum: one file failing doesn't kill the run; you get a row with `fit_quality=bad` and an `error` column.

### Performance note

`molecular_v2` fits with multi-restart can take 400–800 s per spectrum on the 25,000+ N₂(C-B) transitions in your databases. A 14-spectrum batch is ≈ 2 h. Plan accordingly; peak_list and electron_density batches are sub-second per file.

---

## 7. Dashboard

Open `/dashboard`. Pick X and Y axes from any metadata or fit-output column, plus an optional group-by. The dashboard reads all saved fit results from the SQLite DB and plots them in a comparison view.

Use cases:
- Trot(OH) vs pulse frequency, grouped by replicate
- n_e vs cycle count
- Stark FWHM vs voltage

CSV / PNG export buttons live on the Plotly modebar.

---

## 8. Reports

For any analysis result you can produce a **self-contained HTML report** or a **one-page PDF**. Both contain:

- Preprocessing pipeline (operations + parameters)
- Fit model + parameters with stderrs
- Width / intermediate-value chain (Lorentz → vdW → Stark → n_e for density; Trot+Tvib + FWHM for molecular)
- Embedded measured + fit + residuals plot
- Fit-quality classification + warnings
- Calibration provenance (source, Tg used, vdW formula, Stark constant)
- Provenance (metadata, timestamp, database source)

The HTML report has the PNG embedded as base64 so you can email it, paste it into a notebook, or print it to PDF from a browser. The PDF report is rendered via matplotlib's PdfPages backend.

Generate from:
- The **Studio results table header** (HTML report / PDF buttons)
- The **Bands tool Export panel** (HTML report / PDF buttons alongside raw exports)

---

## 9. Atomic and molecular databases

### NIST atomic catalog

`backend/app/databases/atomic/nist_lines.csv` — ~55 curated NIST ASD lines covering H I (Balmer / Paschen α), He I, Ar I + Ar II, O I + O II, N I + N II. Each line carries species, air wavelength, A_ki, accuracy flag, E_i, E_k, g_i, g_k, term symbols, transition label, source, notes.

`backend/app/databases/atomic/nist_live_lines.csv` — optional live cache populated from the Line Database panel's **Refresh from NIST** control. Enter species such as `Ar I, O I, N II`, set the wavelength range, and choose append or replace. The backend queries official NIST ASD tab-delimited output and merges the result into the searchable catalog.

`backend/app/databases/atomic/user_overrides.csv` — optional. Same schema; merged at load time. Use this to add lines NIST doesn't have or to override values without modifying the bundled CSV.

### MassiveOES molecular databases

The SQLite files in `Molecular Line Data/` (one level above `plasma-spec-studio/`) hold MassiveOES-style per-line records:

- `OHAX.db` — 2,160 lines, OH(A-X)
- `N2CB.db` — 195,470 lines, N₂(C-B) Second Positive
- `N2PlusBX.db` — 3,048 lines, N₂⁺(B-X) First Negative
- `NHAX.db` — 2,719 lines, NH(A-X)
- `NOBX.db` — 7,568 lines, NO(B-X)

The store walks up from the backend to find them. Override location with the `PLASMA_SPEC_MOLECULAR_DB_DIR` env var.

---

## 10. Known limitations

- **Synthetic clean H-α lines wider than ~1 nm** show a 10-20 % systematic bias when using the lab's 5 % threshold + normalization workflow. On real noisy data the bias is masked. See `TECHNICAL_NOTES.md` for the explanation.
- **N₂(C-B) multi-restart batches are slow** (400-800 s per spectrum). Use `molecular_v2` recipes sparingly; consider narrower windows when Tvib isn't needed.
- **H-β calibration** is implemented as a literature cross-check (Gigosos-Gonzalez-Konjevic 2003, C=4.84 nm) and explicitly marked `validated=False` — it has not been verified against the user's specific spectrometer.
- **Hönl-London branch factors** are intentionally not applied as additional multipliers because the MassiveOES per-line Einstein A_ki values already encode branch dependence; multiplying by H-L again would double-count. See `TECHNICAL_NOTES.md`.
