"""In-process batch manager with progress events.

A batch run is registered with a UUID and tracked in an in-memory dict. The
run executes in a background thread; fits across spectra run concurrently in a
ThreadPoolExecutor (numpy / scipy release the GIL during their inner loops,
so threads give real parallelism for these fits).

Progress events are delivered to subscribers via an ``asyncio.Queue``-friendly
``stream`` API. SSE endpoints consume the queue to push updates to the
browser.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

from app.core.fitting_utils import flatten_result_for_csv
from app.services.backends.base import Store, get_current_store, set_current_store, use_store
from app.services.batch_service import (
    _long_form_rows,
    _resolve_recipe_kind,
    _run_recipe_on_spectrum,
)
from app.services.export_service import export_batch_csv, export_batch_xlsx
from app.services.spectrum_service import get_spectrum, save_fit_result
from app.preprocessing.pipeline import apply_preprocessing_operations


ProgressEvent = dict[str, Any]


@dataclass
class BatchState:
    """Tracks one batch run from start to finish."""

    batch_id: str
    recipe_kind: str
    total: int
    completed: int = 0
    failed: int = 0
    finished: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    # Final result (set when ``finished`` is True).
    result: dict[str, Any] | None = None
    # Subscribers: asyncio queues that receive events.
    _subscribers: list[asyncio.Queue[ProgressEvent]] = field(default_factory=list)
    # Replay buffer: events that fired before any subscriber connected.
    _history: list[ProgressEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Loop that owns the subscribers (so we can hop threads safely).
    _loop: asyncio.AbstractEventLoop | None = None

    def emit(self, event: ProgressEvent) -> None:
        """Push an event to every subscriber + history. Thread-safe."""

        with self._lock:
            self._history.append(event)
            loop = self._loop
            subscribers = list(self._subscribers)
        if loop is None:
            return
        for queue in subscribers:
            try:
                asyncio.run_coroutine_threadsafe(queue.put(event), loop)
            except RuntimeError:
                # Loop has been closed; drop the event silently.
                continue


# Module-level registry. Keyed by batch_id.
_REGISTRY: dict[str, BatchState] = {}
_REGISTRY_LOCK = threading.Lock()


def get_batch(batch_id: str) -> BatchState:
    with _REGISTRY_LOCK:
        state = _REGISTRY.get(batch_id)
    if state is None:
        raise KeyError(f"unknown batch_id: {batch_id}")
    return state


def list_batches() -> list[dict[str, Any]]:
    """Return a lightweight summary of all known batches."""

    with _REGISTRY_LOCK:
        items = list(_REGISTRY.values())
    return [
        {
            "batch_id": state.batch_id,
            "recipe_kind": state.recipe_kind,
            "total": state.total,
            "completed": state.completed,
            "failed": state.failed,
            "finished": state.finished,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
        }
        for state in items
    ]


def start_batch(
    spectrum_ids: list[str],
    recipe: dict[str, Any],
    *,
    max_workers: int | None = None,
) -> BatchState:
    """Register a batch and kick off its background execution.

    Returns the ``BatchState`` immediately; the caller can subscribe to its
    progress stream or poll for the final result.
    """

    recipe_kind = _resolve_recipe_kind(recipe)
    batch_id = str(uuid4())
    state = BatchState(batch_id=batch_id, recipe_kind=recipe_kind, total=len(spectrum_ids))
    with _REGISTRY_LOCK:
        _REGISTRY[batch_id] = state

    # Capture the calling event loop so worker threads can push events back.
    # Must be called from an async route (or another context with a running
    # loop) -- a freshly constructed loop that nobody ever runs would let
    # `emit()` silently schedule callbacks that never execute.
    try:
        state._loop = asyncio.get_running_loop()
    except RuntimeError:
        state._loop = None

    # Capture the caller's active Store (local or Supabase) so the worker
    # thread -- and the ThreadPoolExecutor threads it spawns -- write fit
    # results as the right user. contextvars don't propagate across plain
    # threading.Thread/ThreadPoolExecutor boundaries the way they do across
    # asyncio tasks, so this has to be threaded through explicitly.
    store = get_current_store()

    thread = threading.Thread(
        target=_run_batch_in_thread,
        args=(state, spectrum_ids, recipe, max_workers, store),
        daemon=True,
        name=f"batch-{batch_id[:8]}",
    )
    thread.start()
    return state


async def subscribe(state: BatchState) -> "asyncio.Queue[ProgressEvent]":
    """Register a fresh asyncio queue for progress events.

    The queue is pre-loaded with any events that already happened so a late
    subscriber sees the full history.
    """

    queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
    with state._lock:
        for event in state._history:
            await queue.put(event)
        state._subscribers.append(queue)
    return queue


def unsubscribe(state: BatchState, queue: "asyncio.Queue[ProgressEvent]") -> None:
    with state._lock:
        try:
            state._subscribers.remove(queue)
        except ValueError:
            pass


# --- Worker implementation -------------------------------------------------


def _run_batch_in_thread(
    state: BatchState,
    spectrum_ids: list[str],
    recipe: dict[str, Any],
    max_workers: int | None,
    store: Store,
) -> None:
    """Run the batch with optional thread-level parallelism."""

    # A fresh threading.Thread starts with no ambient store; this thread
    # owns itself for its whole life (it isn't pooled/reused), so a plain
    # set (no reset) is correct here -- ThreadPoolExecutor workers below
    # (which ARE reused across submissions) instead use use_store() inside
    # _run_one() itself.
    set_current_store(store)
    try:
        rows: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        # numpy/scipy release the GIL during compute, so threads give real
        # parallelism. Cap at (cpu - 1) so the API stays responsive.
        if max_workers is None:
            max_workers = max(1, (os.cpu_count() or 2) - 1)
        # Don't use more workers than spectra.
        max_workers = max(1, min(max_workers, len(spectrum_ids)))

        state.emit(
            {
                "type": "started",
                "batch_id": state.batch_id,
                "recipe_kind": state.recipe_kind,
                "total": state.total,
                "max_workers": max_workers,
            }
        )

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="batchfit") as pool:
            futures = {
                pool.submit(_run_one, spectrum_id, recipe, state.recipe_kind, store): spectrum_id
                for spectrum_id in spectrum_ids
            }
            for future in _as_completed_in_order(futures):
                spectrum_id = futures[future]
                try:
                    result, row_set = future.result()
                except Exception as exc:  # pragma: no cover - per-fit failure path
                    state.failed += 1
                    error_message = str(exc)
                    error_row = {
                        "spectrum_id": spectrum_id,
                        "filename": _safe_filename(spectrum_id),
                        "recipe_kind": state.recipe_kind,
                        "error": error_message,
                        "fit_quality": "bad",
                    }
                    rows.append(error_row)
                    results.append(
                        {
                            "spectrum_id": spectrum_id,
                            "filename": error_row["filename"],
                            "diagnostic": state.recipe_kind,
                            "recipe_kind": state.recipe_kind,
                            "fit_quality": "bad",
                            "warnings": [],
                            "metrics": {},
                            "parameters": {},
                            "metadata": {},
                            "error": error_message,
                        }
                    )
                    state.emit(
                        {
                            "type": "progress",
                            "batch_id": state.batch_id,
                            "completed": state.completed,
                            "failed": state.failed,
                            "total": state.total,
                            "spectrum_id": spectrum_id,
                            "status": "failed",
                            "error": error_message,
                        }
                    )
                else:
                    state.completed += 1
                    save_fit_result(str(uuid4()), result)
                    results.append(result)
                    rows.extend(row_set)
                    state.emit(
                        {
                            "type": "progress",
                            "batch_id": state.batch_id,
                            "completed": state.completed,
                            "failed": state.failed,
                            "total": state.total,
                            "spectrum_id": spectrum_id,
                            "status": "ok",
                            "fit_quality": result.get("fit_quality"),
                        }
                    )

        csv_export = export_batch_csv(rows)
        xlsx_export = export_batch_xlsx(rows)
        result_envelope = {
            "recipe_name": recipe.get("name"),
            "recipe_kind": state.recipe_kind,
            "completed": state.completed,
            "failed": state.failed,
            "results": results,
            "rows": rows,
            "exports": {"csv": csv_export, "xlsx": xlsx_export},
        }
        state.result = result_envelope
        state.finished = True
        state.finished_at = time.time()
        state.emit(
            {
                "type": "finished",
                "batch_id": state.batch_id,
                "completed": state.completed,
                "failed": state.failed,
                "total": state.total,
                "exports": result_envelope["exports"],
                "elapsed_seconds": state.finished_at - state.started_at,
            }
        )
    except Exception as exc:  # pragma: no cover - hard failure path
        state.error = str(exc)
        state.finished = True
        state.finished_at = time.time()
        traceback.print_exc()
        state.emit(
            {
                "type": "error",
                "batch_id": state.batch_id,
                "error": state.error,
            }
        )


def _run_one(
    spectrum_id: str, recipe: dict[str, Any], recipe_kind: str, store: Store
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a single spectrum's analysis and produce its long-form rows.

    Runs on a ThreadPoolExecutor worker thread, which starts with no
    ambient store of its own -- make ``store`` (the batch's owner) current
    for this thread before touching anything in spectrum_service.
    """

    with use_store(store):
        spectrum = get_spectrum(spectrum_id)
        preprocessing = recipe.get("preprocessing") or []
        if preprocessing:
            spectrum = apply_preprocessing_operations(spectrum, preprocessing)
        result = _run_recipe_on_spectrum(spectrum, recipe, recipe_kind)
        rows = _long_form_rows(result, spectrum, recipe_kind)
    return result, rows


def _as_completed_in_order(futures: dict) -> Iterable:
    """concurrent.futures.as_completed, but yields the future objects directly."""

    from concurrent.futures import as_completed

    for fut in as_completed(list(futures.keys())):
        yield fut


def _safe_filename(spectrum_id: str) -> str | None:
    try:
        return get_spectrum(spectrum_id).filename
    except Exception:
        return None
