"""Tests for spectrum deletion, including the fit_results cascade."""

from __future__ import annotations

from uuid import uuid4

import numpy as np

from app.core.spectrum import Spectrum
from app.services.spectrum_service import (
    SPECTRA_DIR,
    delete_spectrum,
    get_spectrum,
    list_fit_results,
    save_fit_result,
    save_spectrum,
)


def _tiny_spectrum(name: str) -> Spectrum:
    x = np.linspace(400.0, 500.0, 50)
    y = np.ones_like(x)
    return save_spectrum(Spectrum(name, x, y))


def test_delete_spectrum_removes_row_array_and_cascades_fit_results():
    spectrum = _tiny_spectrum(f"delete_me_{uuid4().hex}.csv")
    array_path = SPECTRA_DIR / f"{spectrum.id}.csv"
    assert array_path.exists()

    result_id = str(uuid4())
    save_fit_result(result_id, {"spectrum_id": spectrum.id, "diagnostic": "peak_list"})
    assert any(r.get("spectrum_id") == spectrum.id for r in list_fit_results())

    delete_spectrum(spectrum.id)

    assert not array_path.exists(), "array file should be removed from disk"
    try:
        get_spectrum(spectrum.id)
        assert False, "expected KeyError after delete"
    except KeyError:
        pass
    assert not any(r.get("spectrum_id") == spectrum.id for r in list_fit_results()), (
        "fit_results referencing the deleted spectrum should be gone too"
    )


def test_delete_spectrum_raises_key_error_for_unknown_id():
    try:
        delete_spectrum(f"does-not-exist-{uuid4().hex}")
        assert False, "expected KeyError"
    except KeyError:
        pass
