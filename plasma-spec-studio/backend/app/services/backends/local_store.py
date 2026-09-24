"""Local SQLite + local-filesystem ``Store`` implementation.

This is the exact persistence logic PlasmaSpec Studio used before Supabase
support was added, unchanged in behavior -- just organized behind the
``Store`` interface. It's the default backend (``PLASMA_SPEC_STORAGE_BACKEND``
unset or ``local``), so a solo researcher running the app offline, and the
existing pytest suite, need no cloud account at all.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from app.core.json_safe import json_safe
from app.core.spectrum import Spectrum
from app.services.backends.base import Store


BACKEND_ROOT = Path(__file__).resolve().parents[3]
STORAGE_ROOT = Path(
    os.environ.get("PLASMA_SPEC_STORAGE_DIR", str(BACKEND_ROOT / "storage"))
).expanduser()
SPECTRA_DIR = STORAGE_ROOT / "spectra"
EXPORTS_DIR = STORAGE_ROOT / "exports"
DB_PATH = STORAGE_ROOT / "plasma_spec_studio.sqlite3"


class LocalStore(Store):
    def initialize(self) -> None:
        SPECTRA_DIR.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spectra (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    array_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    preprocessing_history_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recipes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    diagnostic TEXT NOT NULL,
                    recipe_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fit_results (
                    id TEXT PRIMARY KEY,
                    spectrum_id TEXT,
                    diagnostic TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    id TEXT PRIMARY KEY,
                    display_name TEXT,
                    avatar_path TEXT,
                    avatar_content_type TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_results (
                    id TEXT PRIMARY KEY,
                    display_name TEXT,
                    avatar_url TEXT,
                    spectrum_filename TEXT,
                    diagnostic TEXT NOT NULL,
                    caption TEXT,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    # -- Spectra --------------------------------------------------------
    def save_spectrum(self, spectrum: Spectrum) -> None:
        self.initialize()
        array_path = SPECTRA_DIR / f"{spectrum.id}.csv"
        pd.DataFrame(
            {"wavelength_nm": spectrum.wavelength_nm, "intensity": spectrum.intensity}
        ).to_csv(array_path, index=False)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO spectra
                (id, filename, array_path, metadata_json, preprocessing_history_json, created_at)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM spectra WHERE id = ?), ?))
                """,
                (
                    spectrum.id,
                    spectrum.filename,
                    str(array_path),
                    json.dumps(json_safe(spectrum.metadata)),
                    json.dumps(json_safe(spectrum.preprocessing_history)),
                    spectrum.id,
                    now,
                ),
            )

    def get_spectrum(self, spectrum_id: str) -> Spectrum:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM spectra WHERE id = ?", (spectrum_id,)).fetchone()
        if row is None:
            raise KeyError(f"spectrum not found: {spectrum_id}")
        frame = pd.read_csv(row["array_path"])
        return Spectrum(
            id=row["id"],
            filename=row["filename"],
            wavelength_nm=frame["wavelength_nm"].to_numpy(dtype=float),
            intensity=frame["intensity"].to_numpy(dtype=float),
            metadata=json.loads(row["metadata_json"]),
            preprocessing_history=json.loads(row["preprocessing_history_json"]),
        )

    def list_spectra(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM spectra ORDER BY created_at DESC").fetchall()
        summaries: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            history = json.loads(row["preprocessing_history_json"])
            try:
                frame = pd.read_csv(row["array_path"], usecols=["wavelength_nm"])
                points = len(frame)
                wl_min = float(frame["wavelength_nm"].min())
                wl_max = float(frame["wavelength_nm"].max())
            except Exception:
                points = None
                wl_min = None
                wl_max = None
            summaries.append(
                {
                    "id": row["id"],
                    "filename": row["filename"],
                    "metadata": metadata,
                    "preprocessing_history": history,
                    "points": points,
                    "wavelength_min_nm": wl_min,
                    "wavelength_max_nm": wl_max,
                    "created_at": row["created_at"],
                }
            )
        return summaries

    # -- Recipes ----------------------------------------------------------
    def save_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        from uuid import uuid4

        recipe_id = recipe.get("id") or str(uuid4())
        now = _now()
        recipe = {**recipe, "id": recipe_id}
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM recipes WHERE id = ?", (recipe_id,)
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO recipes
                (id, name, diagnostic, recipe_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe_id,
                    recipe.get("name", "Untitled recipe"),
                    recipe.get("diagnostic", "analysis"),
                    json.dumps(json_safe(recipe)),
                    created_at,
                    now,
                ),
            )
        return recipe

    def list_recipes(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute("SELECT recipe_json FROM recipes ORDER BY updated_at DESC").fetchall()
        return [json.loads(row["recipe_json"]) for row in rows]

    def get_recipe(self, recipe_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT recipe_json FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            raise KeyError(f"recipe not found: {recipe_id}")
        return json.loads(row["recipe_json"])

    def delete_recipe(self, recipe_id: str) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))

    # -- Fit results --------------------------------------------------------
    def save_fit_result(self, result_id: str, result: dict[str, Any]) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fit_results
                (id, spectrum_id, diagnostic, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    result.get("spectrum_id"),
                    result.get("diagnostic", "analysis"),
                    json.dumps(json_safe(result)),
                    _now(),
                ),
            )

    def list_fit_results(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute("SELECT result_json FROM fit_results ORDER BY created_at DESC").fetchall()
        return [json.loads(row["result_json"]) for row in rows]

    # -- Exports ----------------------------------------------------------
    def save_export(self, export_id: str, kind: str, local_path: Path) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO exports (id, path, kind, created_at) VALUES (?, ?, ?, ?)",
                (export_id, str(local_path), kind, _now()),
            )

    def get_export_bytes(self, export_id: str) -> tuple[bytes, str]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT path FROM exports WHERE id = ?", (export_id,)).fetchone()
        if row is None:
            raise KeyError(f"export not found: {export_id}")
        path = Path(row["path"])
        return path.read_bytes(), path.name

    # -- Profile ----------------------------------------------------------
    _LOCAL_PROFILE_ID = "local"

    def get_profile(self) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name, avatar_path FROM profile WHERE id = ?", (self._LOCAL_PROFILE_ID,)
            ).fetchone()
        return {
            "id": self._LOCAL_PROFILE_ID,
            "email": None,
            "display_name": row["display_name"] if row else None,
            "avatar_url": "/api/profile/avatar" if row and row["avatar_path"] else None,
        }

    def update_profile(self, display_name: str | None) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profile (id, display_name) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name
                """,
                (self._LOCAL_PROFILE_ID, display_name),
            )
        return self.get_profile()

    def save_avatar(self, content: bytes, content_type: str) -> str:
        self.initialize()
        extension = (content_type.split("/")[-1] or "png").split("+")[0]
        avatar_path = STORAGE_ROOT / f"avatar.{extension}"
        avatar_path.write_bytes(content)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profile (id, avatar_path, avatar_content_type) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET avatar_path = excluded.avatar_path,
                    avatar_content_type = excluded.avatar_content_type
                """,
                (self._LOCAL_PROFILE_ID, str(avatar_path), content_type),
            )
        return "/api/profile/avatar"

    def get_avatar_bytes(self) -> tuple[bytes, str]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT avatar_path, avatar_content_type FROM profile WHERE id = ?",
                (self._LOCAL_PROFILE_ID,),
            ).fetchone()
        if row is None or not row["avatar_path"]:
            raise KeyError("no avatar set")
        return Path(row["avatar_path"]).read_bytes(), row["avatar_content_type"] or "image/png"

    # -- Sharing (activity feed) --------------------------------------------
    def share_result(self, result: dict[str, Any], caption: str | None) -> dict[str, Any]:
        self.initialize()
        from uuid import uuid4

        profile = self.get_profile()
        row = {
            "id": str(uuid4()),
            "display_name": profile["display_name"],
            "avatar_url": profile["avatar_url"],
            "spectrum_filename": result.get("filename"),
            "diagnostic": result.get("diagnostic", "analysis"),
            "caption": caption,
            "result_json": json_safe(result),
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shared_results
                (id, display_name, avatar_url, spectrum_filename, diagnostic, caption, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["display_name"],
                    row["avatar_url"],
                    row["spectrum_filename"],
                    row["diagnostic"],
                    row["caption"],
                    json.dumps(row["result_json"]),
                    row["created_at"],
                ),
            )
        return {**row, "user_id": self._LOCAL_PROFILE_ID}

    def list_shared_results(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM shared_results ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "user_id": self._LOCAL_PROFILE_ID,
                "display_name": row["display_name"],
                "avatar_url": row["avatar_url"],
                "spectrum_filename": row["spectrum_filename"],
                "diagnostic": row["diagnostic"],
                "caption": row["caption"],
                "result_json": json.loads(row["result_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_shared_result(self, share_id: str) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute("DELETE FROM shared_results WHERE id = ?", (share_id,))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # sqlite3.Connection's own context-manager protocol only
        # commits/rolls back a transaction -- it does NOT close the
        # connection. Wrap it so it actually closes on exit, and set a
        # busy_timeout so concurrent writers (e.g. a running batch plus a
        # recipe/spectrum save) back off and retry instead of immediately
        # raising "database is locked".
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
