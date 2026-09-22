from __future__ import annotations

import numpy as np

from app.core.line_shapes import voigt
from app.core.spectrum import Spectrum
from app.services.batch_service import run_batch
from app.services.spectrum_service import save_spectrum


def test_batch_runs_recipe_and_isolates_failures():
    x = np.linspace(484, 488, 401)
    y = 4 + 40 * voigt(x, 486.13, 0.06, 0.04)
    spectrum = save_spectrum(Spectrum("batch_hbeta.csv", x, y))
    recipe = {
        "name": "Hbeta batch test",
        "diagnostic": "hbeta_voigt",
        "window_nm": [484, 488],
        "preprocessing": [],
        "fit_model": "voigt",
        "fit_parameters": {
            "center_bounds": [485.8, 486.4],
            "sigma_bounds": [0.001, 1.0],
            "gamma_bounds": [0.001, 1.0],
        },
    }

    result = run_batch([spectrum.id, "missing-spectrum"], recipe)

    assert result["completed"] == 1
    assert result["failed"] == 1
    assert len(result["results"]) == 2
    assert result["results"][0]["fit_quality"] in {"good", "warning"}
    assert result["results"][1]["fit_quality"] == "bad"

