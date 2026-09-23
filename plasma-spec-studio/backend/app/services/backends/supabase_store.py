"""Supabase-backed ``Store``: Postgres for metadata/results, Supabase
Storage for raw files. Always constructed per-request with the *user's own*
access token (never a service-role key) -- every table/storage call below
is executed as that user, so Postgres Row-Level-Security policies (see
``supabase/schema.sql``) are the real enforcement boundary, not the
``.eq("user_id", ...)`` filters here, which are defense-in-depth rather than
the only thing preventing cross-user access.

Storage reads/writes go straight to Supabase's Storage HTTP API via
``httpx`` instead of through ``supabase-py``'s storage wrapper, so behavior
doesn't depend on that SDK's internal handling of bearer tokens across
versions -- the REST contract (``POST/GET .../storage/v1/object/{bucket}/{path}``)
is stable and documented.
"""

from __future__ import annotations

import io
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pandas as pd
from supabase import Client, create_client

from app.core.spectrum import Spectrum
from app.services.backends.base import Store


SPECTRA_BUCKET = "spectra"
EXPORTS_BUCKET = "exports"


class SupabaseStore(Store):
    def __init__(self, supabase_url: str, anon_key: str, access_token: str, user_id: str) -> None:
        self.user_id = user_id
        self._storage_base = f"{supabase_url.rstrip('/')}/storage/v1"
        self._storage_headers = {
            "Authorization": f"Bearer {access_token}",
            "apikey": anon_key,
        }
        self.client: Client = create_client(supabase_url, anon_key)
        # Makes every postgrest call below run as this user, so RLS applies.
        self.client.postgrest.auth(access_token)

    def initialize(self) -> None:
        # Schema + buckets are provisioned once via supabase/schema.sql, run
        # by the project owner in the Supabase SQL editor -- nothing to do
        # per-request here.
        pass

    # -- Storage helpers --------------------------------------------------
    def _storage_upload(self, bucket: str, path: str, content: bytes, content_type: str) -> None:
        url = f"{self._storage_base}/object/{bucket}/{path}"
        headers = {**self._storage_headers, "Content-Type": content_type, "x-upsert": "true"}
        response = httpx.post(url, headers=headers, content=content, timeout=60.0)
        if response.status_code >= 300:
            raise RuntimeError(
                f"Supabase Storage upload to {bucket}/{path} failed "
                f"({response.status_code}): {response.text}"
            )

    def _storage_download(self, bucket: str, path: str) -> bytes:
        url = f"{self._storage_base}/object/{bucket}/{path}"
        response = httpx.get(url, headers=self._storage_headers, timeout=60.0)
        if response.status_code == 404:
            raise KeyError(f"storage object not found: {bucket}/{path}")
        if response.status_code >= 300:
            raise RuntimeError(
                f"Supabase Storage download of {bucket}/{path} failed "
                f"({response.status_code}): {response.text}"
            )
        return response.content

    def _spectrum_storage_path(self, spectrum_id: str) -> str:
        return f"{self.user_id}/{spectrum_id}.csv"

    # -- Spectra --------------------------------------------------------
    def save_spectrum(self, spectrum: Spectrum) -> None:
        buffer = io.StringIO()
        pd.DataFrame(
            {"wavelength_nm": spectrum.wavelength_nm, "intensity": spectrum.intensity}
        ).to_csv(buffer, index=False)
        storage_path = self._spectrum_storage_path(spectrum.id)
        self._storage_upload(SPECTRA_BUCKET, storage_path, buffer.getvalue().encode("utf-8"), "text/csv")

        existing = (
            self.client.table("spectra")
            .select("created_at")
            .eq("id", spectrum.id)
            .eq("user_id", self.user_id)
            .execute()
        )
        created_at = existing.data[0]["created_at"] if existing.data else _now()
        wavelength = spectrum.wavelength_nm
        row = {
            "id": spectrum.id,
            "user_id": self.user_id,
            "filename": spectrum.filename,
            "storage_path": storage_path,
            "metadata": spectrum.metadata,
            "preprocessing_history": spectrum.preprocessing_history,
            "points": int(len(wavelength)),
            "wavelength_min_nm": float(wavelength.min()) if len(wavelength) else None,
            "wavelength_max_nm": float(wavelength.max()) if len(wavelength) else None,
            "created_at": created_at,
            "updated_at": _now(),
        }
        self.client.table("spectra").upsert(row, on_conflict="id").execute()

    def get_spectrum(self, spectrum_id: str) -> Spectrum:
        result = (
            self.client.table("spectra")
            .select("*")
            .eq("id", spectrum_id)
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise KeyError(f"spectrum not found: {spectrum_id}")
        row = result.data[0]
        content = self._storage_download(SPECTRA_BUCKET, row["storage_path"])
        frame = pd.read_csv(io.BytesIO(content))
        return Spectrum(
            id=row["id"],
            filename=row["filename"],
            wavelength_nm=frame["wavelength_nm"].to_numpy(dtype=float),
            intensity=frame["intensity"].to_numpy(dtype=float),
            metadata=row.get("metadata") or {},
            preprocessing_history=row.get("preprocessing_history") or [],
        )

    def list_spectra(self) -> list[dict[str, Any]]:
        result = (
            self.client.table("spectra")
            .select("*")
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "metadata": row.get("metadata") or {},
                "preprocessing_history": row.get("preprocessing_history") or [],
                "points": row.get("points"),
                "wavelength_min_nm": row.get("wavelength_min_nm"),
                "wavelength_max_nm": row.get("wavelength_max_nm"),
                "created_at": row.get("created_at"),
            }
            for row in result.data
        ]

    # -- Recipes ----------------------------------------------------------
    def save_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]:
        recipe_id = recipe.get("id") or str(uuid4())
        recipe = {**recipe, "id": recipe_id}
        existing = (
            self.client.table("recipes")
            .select("created_at")
            .eq("id", recipe_id)
            .eq("user_id", self.user_id)
            .execute()
        )
        created_at = existing.data[0]["created_at"] if existing.data else _now()
        row = {
            "id": recipe_id,
            "user_id": self.user_id,
            "name": recipe.get("name", "Untitled recipe"),
            "diagnostic": recipe.get("diagnostic", "analysis"),
            "recipe_json": recipe,
            "created_at": created_at,
            "updated_at": _now(),
        }
        self.client.table("recipes").upsert(row, on_conflict="id").execute()
        return recipe

    def list_recipes(self) -> list[dict[str, Any]]:
        result = (
            self.client.table("recipes")
            .select("recipe_json")
            .eq("user_id", self.user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return [row["recipe_json"] for row in result.data]

    def get_recipe(self, recipe_id: str) -> dict[str, Any]:
        result = (
            self.client.table("recipes")
            .select("recipe_json")
            .eq("id", recipe_id)
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise KeyError(f"recipe not found: {recipe_id}")
        return result.data[0]["recipe_json"]

    def delete_recipe(self, recipe_id: str) -> None:
        self.client.table("recipes").delete().eq("id", recipe_id).eq("user_id", self.user_id).execute()

    # -- Fit results --------------------------------------------------------
    def save_fit_result(self, result_id: str, result: dict[str, Any]) -> None:
        row = {
            "id": result_id,
            "user_id": self.user_id,
            "spectrum_id": result.get("spectrum_id"),
            "diagnostic": result.get("diagnostic", "analysis"),
            "result_json": result,
            "created_at": _now(),
        }
        self.client.table("fit_results").upsert(row, on_conflict="id").execute()

    def list_fit_results(self) -> list[dict[str, Any]]:
        result = (
            self.client.table("fit_results")
            .select("result_json")
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [row["result_json"] for row in result.data]

    # -- Exports ----------------------------------------------------------
    def save_export(self, export_id: str, kind: str, local_path: Path) -> None:
        content = local_path.read_bytes()
        storage_path = f"{self.user_id}/{local_path.name}"
        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        self._storage_upload(EXPORTS_BUCKET, storage_path, content, content_type)
        row = {
            "id": export_id,
            "user_id": self.user_id,
            "storage_path": storage_path,
            "kind": kind,
            "created_at": _now(),
        }
        self.client.table("exports").upsert(row, on_conflict="id").execute()

    def get_export_bytes(self, export_id: str) -> tuple[bytes, str]:
        result = (
            self.client.table("exports")
            .select("storage_path")
            .eq("id", export_id)
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise KeyError(f"export not found: {export_id}")
        storage_path = result.data[0]["storage_path"]
        content = self._storage_download(EXPORTS_BUCKET, storage_path)
        return content, Path(storage_path).name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
