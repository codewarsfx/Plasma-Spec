# Plasma Spec App

A research repository for optical-emission-spectroscopy (OES) diagnostics of
low-temperature plasmas. The centerpiece is **PlasmaSpec Studio**, a
full-stack diagnostics workstation that takes a raw spectrum all the way to
traceable, publication-ready plasma parameters — with every intermediate
value visible along the way.

## What's in here

| Path | What it is |
| --- | --- |
| [`plasma-spec-studio/`](plasma-spec-studio/) | The application: FastAPI backend + Next.js frontend + Electron desktop packaging. See its [README](plasma-spec-studio/README.md) for the full feature list. |
| `Molecular Line Data/` | Raw/working molecular line data used by the diagnostics (git-ignored — not tracked in this repo). |

## PlasmaSpec Studio, in brief

Inspired by SpecAir and MassiveOES, PlasmaSpec Studio is built as a
single-page workstation for low-temperature plasma diagnostics (e.g.
atmospheric-pressure jets, DBDs, nanosecond-pulsed and gas–liquid discharges):

- **Import & QA** — CSV/TXT/TSV/ASC/DAT/XLSX spectra with auto-detected
  columns, Avantes metadata parsing, and pre-fit spectrum quality checks.
- **Preprocessing** — crop, wavelength calibration, ALS baseline, spike
  removal, Savitzky–Golay smoothing, background subtraction, all logged.
- **Peak analysis** — per-line height / area / FWHM / SNR, optional
  Gaussian/Lorentzian/Voigt fits, built-in low-temperature-plasma marker
  presets (OH, N₂, NH, N₂⁺, H, O, Ar) with standard diagnostic ratios.
- **Atomic line ID & forward modelling** against a bundled NIST-derived
  catalog, with live NIST ASD refresh support.
- **Molecular band fitting** (MassiveOES-style, OH/N₂/N₂⁺/NH/NO) for true
  two-temperature (T_rot + T_vib) fits, including a state-by-state mode that
  doesn't assume a Boltzmann distribution.
- **Electron density** from H-α Stark broadening — a faithful port of the
  lab's MATLAB workflow (Gigosos–Cardeñoso conversion, single/two-Voigt).
- **Recipes, batch processing, dashboards, and reports** for turning a
  single fit into a repeatable, comparable, exportable pipeline.

### Quick start

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

Then open <http://localhost:3000/studio>. Full docs live in
[`plasma-spec-studio/`](plasma-spec-studio/): the
[user guide](plasma-spec-studio/USER_GUIDE.md), the
[technical notes](plasma-spec-studio/TECHNICAL_NOTES.md) (math and
literature references behind every diagnostic), and the
[desktop release guide](plasma-spec-studio/DESKTOP_RELEASE.md).

## About the creator

This project is built by **Chidera**, a Chemical Engineering Ph.D. candidate
at the FAMU-FSU College of Engineering. Chidera's research sits at the
intersection of non-thermal plasma, sustainable chemical processes, PFAS
destruction, plasma diagnostics, and machine learning — PlasmaSpec Studio
grew directly out of the need for a faster, more traceable way to turn raw
OES spectra from the lab into real diagnostic numbers.

Alongside the research, Chidera has a strong software-development
background and enjoys building web and app products, which is the mix of
experimental engineering and computational skills behind this workstation.
Outside the lab, Chidera is active in leadership and STEM outreach —
including volunteering with programs that introduce younger students to
science and engineering — and spends free time hiking, working on side
projects, and learning guitar.
