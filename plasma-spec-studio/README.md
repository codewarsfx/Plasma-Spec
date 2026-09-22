# PlasmaSpec Studio

An optical-emission-spectroscopy diagnostics workstation for low-temperature plasma experiments. Inspired by SpecAir and MassiveOES; built as a single-page workstation that goes from raw spectrum to traceable diagnostics with every intermediate value visible.

## What it does

- **Import** CSV / TXT / TSV / ASC / DAT / XLSX spectra. Auto-detect wavelength + intensity columns. Parse Avantes-style metadata headers from .xlsx. Parse filenames like `100kHz_1ms_10_1.xlsx` into experimental metadata.
- **Spectrum QA** checks point count, wavelength spacing/jitter, SNR estimate, negative offsets, flat-top saturation, edge baseline drift, spike-like outliers, and diagnostic wavelength coverage before fitting.
- **Preprocess** with crop, matched-line wavelength calibration, ALS baseline (Eilers-Boelens), max normalize, spike removal (median-filter outliers), Savitzky-Golay smoothing, background subtraction. Every operation logged in the spectrum's preprocessing history.
- **Wavelength-list peak analysis**: paste a list of wavelengths of interest, get per-peak height / integrated area / baseline-subtracted area / FWHM / SNR for each. Optionally fit Gaussian / Lorentzian / Voigt + linear baseline per peak with proper parameter stderrs. Built-in low-temperature plasma marker presets cover OH, N2, NH, N2+, H, O, and Ar lines, with automatic ratios such as H-alpha/H-beta, N2+/N2, OH/N2, O 777/844, and Ar 750/811.
- **Atomic line identification** against a bundled NIST-derived catalog plus optional live NIST ASD refresh coverage.
- **Atomic forward modelling** with the NIST catalog: relative optically thin LTE-style atomic spectra, fitted excitation temperature, species scales, wavelength shift, Gaussian/Voigt instrument width, baseline, residuals, and strongest-line contribution table.
- **Molecular band fitting** using the provided MassiveOES-style species line databases (OH(A-X), N2(C-B), N2+(B-X), NH(A-X), NO(B-X)) for true two-temperature (Trot + Tvib) fits with Voigt instrument profile and multi-restart driver. Parameter stderrs from the Jacobian.
- **State-by-state molecular fitting** for temperature-independent upper-state populations. The fit does not impose a Boltzmann distribution; it reports relative state populations plus post-fit Boltzmann-plot slopes by v' manifold.
- **Electron density** from H-α (or H-β cross-check) Stark broadening — a faithful port of the user's lab MATLAB scripts. Linear vdW subtraction, Gigosos-Cardeñoso conversion with the lab's C = 1.78 nm constant, single-Voigt and two-Voigt models. Full width chain (instrument Gauss → fitted Lorentz → vdW → Stark → n_e) reported with 95 % CI.
- **Recipes** save analysis configurations (peak_list, molecular_v2, electron_density). Re-apply to any spectrum or batch.
- **Batch processing** runs a recipe across many spectra and produces long-form CSV + XLSX tables (one row per peak × spectrum for peak_list batches; one row per spectrum for molecular / density).
- **Dashboard** compares saved fit results against any metadata key (frequency, cycles, gas, voltage, replicate).
- **Reports**: per-result self-contained HTML or one-page PDF with the full math + preprocessing + parameters + plot + residuals + warnings + provenance.

## Quick start

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

Open <http://localhost:3000/studio>.

Run the backend tests:

```bash
cd plasma-spec-studio/backend
.venv/bin/pytest         # fast suite (~64 tests, ~5 s)
.venv/bin/pytest -m slow # slow suite (Tvib + multi-restart, ~12 min)
```

## Documentation

- [`USER_GUIDE.md`](USER_GUIDE.md) — how to use each tool, written in the order you'd touch them during an experiment.
- [`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md) — math, assumptions, and literature references for every diagnostic.
- [`DESKTOP_RELEASE.md`](DESKTOP_RELEASE.md) — how to build downloadable macOS DMG and Windows EXE installers.

## Desktop Installers

The app can be packaged as a desktop download with Electron plus a PyInstaller backend sidecar:

```bash
npm run dist:mac
npm run dist:win
```

Installer artifacts are written to `release/`. GitHub Actions also builds DMG and EXE artifacts from `.github/workflows/desktop-release.yml`.

## Project layout

```
plasma-spec-studio/
  backend/
    app/
      analysis/
        electron_density/    Stark workflow (Gigosos H-α lab port, single + two Voigt)
        peaks/               wavelength-list peak analysis
      api/                   FastAPI routes
      core/                  Spectrum, line shapes, fitting utilities
      databases/
        atomic/              NIST-derived catalog + sources.json
        molecular/           MassiveOES SQLite path resolution + transitions loader
      models/                H-β Voigt fitter (legacy), molecular band fitter, peak area, atomic ID
      preprocessing/         importers (text + Excel), baseline, smoothing, spike removal, filename metadata
      schemas/               Pydantic request/response models
      services/              spectrum storage, recipe storage, batch runner, export, report generator
      tests/                 pytest tests (fast + slow markers)
  frontend/
    app/
      studio/                Workstation (primary)
      spectra, batch, dashboard, recipes  Focused workflows wrapped in a unified LegacyPageShell
    components/
      studio/                Workstation shell components
      Toast.tsx              In-app toast notifications
      WavelengthListPanel.tsx, AtomicLineSearchPanel.tsx, FittingPanel.tsx,
      ElectronDensityPanel.tsx, PreprocessingPanel.tsx, RecipeEditor.tsx, BatchProcessor.tsx,
      DashboardComparison.tsx, MetadataTable.tsx, SpectrumPlot.tsx, SpectrumUploader.tsx,
      ResidualPlot.tsx, ExportPanel.tsx, FitResultCard.tsx, DiagnosticSelector.tsx
  sample_data/
    spectra/                 Real OES spectra (XLSX from Avantes spectrometer) + synthetic demos
    metadata/                Experiment metadata CSV
    recipes/                 Demo recipe JSON
    phase2_real_data_validation.csv   OH / N2 Trot + Tvib results across 4 freqs
    phase3_real_data_validation.csv   Electron density results on H-α spectra
```

## Sample data

The repository includes 14 real spectra plus 3 synthetic demo spectra:

- **`100/250/500/750 kHz_1ms_10_{1,2,3}.xlsx`** — 12 UV spectra (296-408 nm) at four pulse frequencies × three replicates. Cover OH(A-X), N₂(C-B) v=0,1,2, N₂⁺ 391.
- **`1khz_t1.xlsx`** — high-resolution 597-712 nm spectrum (0.032 nm step). Covers H-α + Ar I 696/706.
- **`1khz-argon.xlsx`** — wide visible/NIR 596-1094 nm spectrum. Covers H-α + the full Ar I series (696-922 nm) + O I 777 + O I 844.
- **`demo_ns_plasma_*.csv`** — original synthetic demo spectra (300-850 nm, kept for backward-compat tests).

## Databases

**Atomic catalog** (`backend/app/databases/atomic/nist_lines.csv`) — bundled NIST-derived subset (~55 lines) of the species most relevant to low-temperature plasma OES. The Line Database panel can refresh official NIST ASD coverage on demand into `nist_live_lines.csv` for any species/range, and `user_overrides.csv` still sits on top for manual corrections or lab-specific lines.

**Molecular databases** (`Molecular Line Data/*.db`, one level above this directory) — provided MassiveOES-style SQLite line lists:

| File | Species | Lines | Range |
|---|---|---|---|
| `OHAX.db` | OH(A-X) | 2,160 | 278.7-368.2 nm |
| `N2CB.db` | N₂(C-B) Second Positive | 195,470 | 259.2-720.6 nm |
| `N2PlusBX.db` | N₂⁺(B-X) First Negative | 3,048 | 340.7-391.6 nm |
| `NHAX.db` | NH(A-X) | 2,719 | 307.1-439.5 nm |
| `NOBX.db` | NO(B-X) β system | 7,568 | 357.0-425.0 nm |

The store walks up from the backend to find them; override the location with `PLASMA_SPEC_MOLECULAR_DB_DIR`.

## Scientific honesty

- Every diagnostic result includes the full intermediate-value chain (preprocessing → fit parameters → derived values like Stark FWHM → physical quantity like n_e), parameter stderrs, fit quality classification, and explicit warnings (bounds near limit, low SNR, calibration not validated, etc.).
- The atomic and molecular spectroscopic inputs are reference-backed: a bundled NIST-derived atomic catalog plus the provided MassiveOES-style species line databases. That provenance supports line identification and forward models; "software-tested" describes the fitting code path, not independent experimental validation of derived Trot, Tvib, or n_e values.
- The atomic forward model is relative, optically thin, and LTE-style. Species scales absorb partition functions, collection efficiency, path length, and calibration; it does not include radiation transport, self-absorption, quenching, or non-Boltzmann kinetics.
- The H-α electron density workflow is a faithful port of the user's lab MATLAB scripts; cross-check by running the originals before using it as a primary measurement.
- The H-β calibration is a literature cross-check (C = 4.84 nm, Gigosos-González-Konjević 2003) marked `validated=False` — not verified against the lab spectrometer.
- Hönl-London branch factors are intentionally not applied because the MassiveOES per-line A_ki values already encode branch dependence. See `TECHNICAL_NOTES.md` §3.2.

## Status

| Phase | Done |
|---|---|
| 1 — DBs + wavelength-list workflow | ✓ |
| 2 — Two-T molecular fits + Voigt + multi-restart | ✓ |
| 2b — State-by-state molecular populations | ✓ |
| 2c — Matched-line wavelength calibration | ✓ |
| 2d — Spectrum QA + plasma marker ratios | ✓ |
| 3 — Electron density (lab MATLAB port) | ✓ |
| 4 — Recipes + batch | ✓ |
| 5 — Workstation UI | ✓ |
| 6 — Reporting + docs | ✓ |
| Optional polish — NIST live refresh | ✓ |
| Research feature — atomic forward model | ✓ |
| Optional polish — parallel batch | pending |

Backend: 76 fast tests + 6 slow tests, all green.
Frontend: TypeScript clean, production build clean (10 static routes). Lint uses the ESLint CLI.
