"""The ``Store`` interface every persistence backend implements, plus the
ambient "current store" mechanism.

Rather than threading a ``store`` parameter through every function in
``fitting_service``/``batch_service``/``export_service``/``report_service``
(which would touch nearly every module in the backend for a concern those
modules don't actually care about), the active backend is kept in a
``contextvars.ContextVar``. A FastAPI dependency sets it for the duration of
each request (see ``app.auth.require_store``); ``spectrum_service`` and
``recipe_service`` read it internally via ``get_current_store()`` so their
public function signatures are unchanged and every existing caller
(including all the science/analysis code and the existing test suite, which
calls these functions directly without going through a route at all) keeps
working exactly as before.

When nothing has set the context var -- e.g. a unit test calling
``save_spectrum(...)`` directly, or the app running with no
``PLASMA_SPEC_STORAGE_BACKEND`` configured at all -- ``get_current_store()``
falls back to a lazily-constructed local ``LocalStore`` singleton, so local
single-user usage (and the existing pytest suite) needs zero Supabase setup.

Batch runs execute on a plain ``threading.Thread`` (and a ``ThreadPoolExecutor``
inside it), and contextvars do NOT automatically propagate across OS thread
boundaries the way they do across asyncio tasks. ``batch_manager.py``
therefore captures ``get_current_store()`` explicitly before spawning its
worker thread and re-applies it with ``use_store()`` at the top of each
worker callable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from app.core.spectrum import Spectrum


class Store(ABC):
    """Everything the app needs to persist spectra, recipes, fit results,
    and generated exports -- implemented once per backend (local SQLite,
    Supabase)."""

    def initialize(self) -> None:
        """Prepare storage (create tables/dirs). No-op for backends where
        the schema is managed externally (e.g. Supabase's SQL migration)."""

    # -- Spectra --------------------------------------------------------
    @abstractmethod
    def save_spectrum(self, spectrum: Spectrum) -> None: ...

    @abstractmethod
    def get_spectrum(self, spectrum_id: str) -> Spectrum:
        """Raise KeyError if not found."""

    @abstractmethod
    def list_spectra(self) -> list[dict[str, Any]]:
        """Summaries (no full arrays) for the spectra list UI."""

    # -- Recipes ----------------------------------------------------------
    @abstractmethod
    def save_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def list_recipes(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_recipe(self, recipe_id: str) -> dict[str, Any]:
        """Raise KeyError if not found."""

    @abstractmethod
    def delete_recipe(self, recipe_id: str) -> None: ...

    # -- Fit results --------------------------------------------------------
    @abstractmethod
    def save_fit_result(self, result_id: str, result: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_fit_results(self) -> list[dict[str, Any]]: ...

    # -- Exports ----------------------------------------------------------
    @abstractmethod
    def save_export(self, export_id: str, kind: str, local_path: Path) -> None:
        """Record (and for cloud backends, upload) a file that report_service
        / export_service already wrote to a local path."""

    @abstractmethod
    def get_export_bytes(self, export_id: str) -> tuple[bytes, str]:
        """Return (content, filename). Raise KeyError if not found."""


_current_store: ContextVar[Store | None] = ContextVar("plasma_spec_current_store", default=None)
_default_local_store: Store | None = None


def get_current_store() -> Store:
    store = _current_store.get()
    if store is not None:
        return store
    global _default_local_store
    if _default_local_store is None:
        # Deferred import: local_store.py imports Store from this module, so
        # importing it at module load time here would be circular.
        from app.services.backends.local_store import LocalStore

        _default_local_store = LocalStore()
    return _default_local_store


@contextmanager
def use_store(store: Store) -> Iterator[Store]:
    """Make ``store`` the ambient store for everything inside this block,
    including code running on the same thread that later reads it back out
    via ``get_current_store()``."""

    token = _current_store.set(store)
    try:
        yield store
    finally:
        _current_store.reset(token)


def set_current_store(store: Store) -> None:
    """Set the ambient store for the rest of the current thread's life, with
    no reset. For a plain ``threading.Thread`` target that owns its thread
    for its full lifetime (e.g. a batch worker thread) rather than a
    request/task that must hand the thread back afterward -- prefer
    ``use_store()`` for anything scoped (requests, ThreadPoolExecutor tasks
    that reuse pool threads across calls)."""

    _current_store.set(store)
