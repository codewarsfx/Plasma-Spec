"""Endpoints for browsing the bundled spectroscopic databases."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.databases.atomic import nist_client
from app.databases.atomic import store as atomic_store
from app.databases.molecular import store as molecular_store


router = APIRouter(prefix="/api/databases", tags=["databases"])

ATOMIC_OVERRIDES_PATH = Path(atomic_store.USER_OVERRIDE_CSV)
ATOMIC_OVERRIDE_REQUIRED_COLUMNS = ("species", "wavelength_air_nm")


class AtomicNistRefreshRequest(BaseModel):
    """Official NIST ASD refresh request.

    Empty ``species`` falls back to common low-temperature plasma atoms/ions.
    This is intentionally range-scoped: querying "All spectra" across all NIST
    wavelengths is not a publishable app workflow, it is a denial-of-service
    invitation and impossible to validate locally.
    """

    species: list[str] = Field(default_factory=list)
    wavelength_min_nm: float | None = 200.0
    wavelength_max_nm: float | None = 1100.0
    mode: Literal["append", "replace"] = "append"
    require_transition_probabilities: bool = False
    max_lines_per_species: int = Field(default=20_000, ge=1, le=100_000)
    timeout_s: float = Field(default=30.0, ge=5.0, le=120.0)


@router.get("/molecular")
def list_molecular_databases() -> dict:
    return {
        "root": str(molecular_store.molecular_db_root() or ""),
        "species": molecular_store.list_species(),
    }


@router.get("/atomic/summary")
def atomic_summary() -> dict:
    return atomic_store.catalog_summary()


@router.get("/atomic/species")
def atomic_species() -> dict:
    return {"species": atomic_store.list_species()}


@router.post("/atomic/refresh")
def refresh_atomic_from_nist(payload: AtomicNistRefreshRequest) -> dict:
    """Fetch official NIST ASD lines into the local live-cache catalog."""

    requested_species = [
        item.strip()
        for item in (
            payload.species or nist_client.DEFAULT_LOW_TEMPERATURE_PLASMA_SPECIES
        )
        if item.strip()
    ]
    if not requested_species:
        raise HTTPException(status_code=400, detail="at least one species is required")

    frames = []
    fetched: list[dict] = []
    failures: list[dict] = []
    for species in requested_species:
        try:
            result = nist_client.fetch_nist_lines(
                species=species,
                wavelength_min_nm=payload.wavelength_min_nm,
                wavelength_max_nm=payload.wavelength_max_nm,
                require_transition_probabilities=payload.require_transition_probabilities,
                max_lines=payload.max_lines_per_species,
                timeout_s=payload.timeout_s,
            )
            if not result.lines.empty:
                frames.append(result.lines)
            fetched.append(
                {
                    "species": result.species,
                    "line_count": result.line_count,
                    "url": result.url,
                    "ssl_verified": result.ssl_verified,
                }
            )
        except Exception as exc:
            failures.append({"species": species, "error": str(exc)})

    if not frames:
        raise HTTPException(
            status_code=502 if failures else 400,
            detail={
                "message": "NIST refresh returned no usable lines",
                "requested_species": requested_species,
                "failures": failures,
            },
        )

    import pandas as pd

    combined = pd.concat(frames, ignore_index=True)
    live_cache = atomic_store.write_nist_live_lines(combined, mode=payload.mode)
    summary = atomic_store.catalog_summary()
    return {
        "status": "partial" if failures else "ok",
        "requested_species": requested_species,
        "fetched": fetched,
        "failures": failures,
        "imported_rows": int(len(combined)),
        "live_cache": live_cache,
        "catalog_summary": summary,
        "nist_endpoint": nist_client.NIST_LINES_ENDPOINT,
        "mode": payload.mode,
    }


@router.post("/atomic/overrides")
async def upload_atomic_overrides(
    file: Annotated[UploadFile, File(description="CSV with columns: species, wavelength_air_nm, A_ki_s_1?, E_k_cm1?, g_k?, ...")],
    mode: Annotated[str, Form()] = "append",
) -> dict:
    """Merge a user-supplied atomic line CSV into ``user_overrides.csv``.

    The schema matches the bundled NIST catalog: ``species`` and
    ``wavelength_air_nm`` are required; ``A_ki_s_1``, ``E_i_cm1``,
    ``E_k_cm1``, ``g_i``, ``g_k``, ``acc_A``, ``lower_term``, ``upper_term``,
    ``transition``, ``source``, ``notes`` are optional.

    To populate from NIST ASD: query
    https://physics.nist.gov/cgi-bin/ASD/lines1.pl manually (or via the
    ``astroquery.nist`` package outside the app), export as CSV, rename the
    columns to match the bundled schema, and upload here.

    ``mode``: ``"append"`` (default) merges with the existing overrides;
    ``"replace"`` overwrites them entirely.
    """

    if mode not in {"append", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be 'append' or 'replace'")
    content = await file.read()
    try:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        missing = [c for c in ATOMIC_OVERRIDE_REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        new_rows = [row for row in reader if row.get("species") and row.get("wavelength_air_nm")]
        if not new_rows:
            raise ValueError("CSV has zero valid rows after filtering empty species/wavelength")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ATOMIC_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and ATOMIC_OVERRIDES_PATH.exists():
        with ATOMIC_OVERRIDES_PATH.open(encoding="utf-8-sig") as fp:
            existing_reader = csv.DictReader(fp)
            existing_rows = list(existing_reader)
            existing_fieldnames = existing_reader.fieldnames or []
        combined_fieldnames = list(
            dict.fromkeys([*existing_fieldnames, *(reader.fieldnames or [])])
        )
        combined_rows = existing_rows + new_rows
    else:
        combined_fieldnames = list(reader.fieldnames or [])
        combined_rows = new_rows

    with ATOMIC_OVERRIDES_PATH.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=combined_fieldnames)
        writer.writeheader()
        for row in combined_rows:
            writer.writerow({k: row.get(k, "") for k in combined_fieldnames})

    atomic_store.reset_cache()
    summary = atomic_store.catalog_summary()
    return {
        "status": "ok",
        "appended_rows": len(new_rows),
        "total_overrides": len(combined_rows),
        "catalog_summary": summary,
        "overrides_path": str(ATOMIC_OVERRIDES_PATH),
    }


@router.get("/atomic/search")
def atomic_search(
    species: Annotated[list[str] | None, Query()] = None,
    wavelength_min_nm: float | None = None,
    wavelength_max_nm: float | None = None,
    near_nm: float | None = None,
    tolerance_nm: float = 0.5,
    require_einstein: bool = False,
    energy_upper_max_cm1: float | None = None,
    max_results: int = 200,
) -> dict:
    try:
        results = atomic_store.search_lines(
            species=species,
            wavelength_min_nm=wavelength_min_nm,
            wavelength_max_nm=wavelength_max_nm,
            near_nm=near_nm,
            tolerance_nm=tolerance_nm,
            energy_upper_max_cm1=energy_upper_max_cm1,
            require_einstein=require_einstein,
            max_results=max_results,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": len(results), "results": results}
