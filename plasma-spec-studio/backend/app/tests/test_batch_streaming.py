"""Tests for the streaming + parallel batch manager."""

from __future__ import annotations

import time

import numpy as np
import pytest

from app.core.line_shapes import voigt
from app.core.spectrum import Spectrum
from app.services.batch_manager import get_batch, list_batches, start_batch
from app.services.spectrum_service import save_spectrum


def _store_three_peak_spectrum(name: str, seed: int = 0) -> Spectrum:
    rng = np.random.default_rng(seed)
    x = np.linspace(300.0, 800.0, 4001)
    y = 5.0 + 0.0
    for c, a, s, g in [(310.0, 180, 0.08, 0.04), (486.135, 140, 0.05, 0.03), (656.279, 220, 0.06, 0.04)]:
        y = y + a * voigt(x, c, s, g)
    y = y + rng.normal(0.0, 0.1, size=len(x))
    return save_spectrum(Spectrum(name, x, y))


def test_streaming_batch_completes_and_emits_progress():
    spectra = [_store_three_peak_spectrum(f"stream_{i}.csv", seed=i) for i in range(4)]
    recipe = {
        "name": "stream-test",
        "diagnostic": "peak_list",
        "recipe_kind": "peak_list",
        "peak_list": {
            "peaks": [
                {"label": "Hbeta", "center_nm": 486.135, "half_width_nm": 1.0},
                {"label": "Halpha", "center_nm": 656.279, "half_width_nm": 1.0},
            ],
        },
    }
    state = start_batch([s.id for s in spectra], recipe, max_workers=2)
    # Wait for completion (peak_list is sub-second per spectrum even at 4 files).
    deadline = time.time() + 30
    while not state.finished and time.time() < deadline:
        time.sleep(0.05)
    assert state.finished, "batch did not finish within 30 s"
    assert state.completed == 4
    assert state.failed == 0
    assert state.result is not None
    # Long-form rows: 2 peaks * 4 spectra = 8
    assert len(state.result["rows"]) == 8

    # Progress events should include started + 4 progress + finished
    events = state._history
    types = [event["type"] for event in events]
    assert types[0] == "started"
    assert types[-1] == "finished"
    assert types.count("progress") == 4


def test_get_batch_raises_for_unknown_id():
    with pytest.raises(KeyError):
        get_batch("nonexistent")


def test_list_batches_includes_recent_run():
    spectra = [_store_three_peak_spectrum(f"list_{i}.csv", seed=10 + i) for i in range(2)]
    recipe = {
        "name": "list-test",
        "diagnostic": "peak_list",
        "recipe_kind": "peak_list",
        "peak_list": {"peaks": [{"label": "Hb", "center_nm": 486.135, "half_width_nm": 1.0}]},
    }
    state = start_batch([s.id for s in spectra], recipe, max_workers=1)
    deadline = time.time() + 30
    while not state.finished and time.time() < deadline:
        time.sleep(0.05)
    ids = [item["batch_id"] for item in list_batches()]
    assert state.batch_id in ids


def test_max_workers_capped_at_n_spectra():
    """If only 2 spectra are queued, we shouldn't oversubscribe with 8 workers."""

    spectra = [_store_three_peak_spectrum(f"cap_{i}.csv", seed=30 + i) for i in range(2)]
    recipe = {
        "name": "cap-test",
        "diagnostic": "peak_list",
        "recipe_kind": "peak_list",
        "peak_list": {"peaks": [{"label": "Hb", "center_nm": 486.135, "half_width_nm": 1.0}]},
    }
    state = start_batch([s.id for s in spectra], recipe, max_workers=8)
    deadline = time.time() + 30
    while not state.finished and time.time() < deadline:
        time.sleep(0.05)
    started = next(event for event in state._history if event.get("type") == "started")
    assert started["max_workers"] == 2  # capped to n_spectra
