"""FastAPI application for PlasmaSpec Studio."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    batch_routes,
    databases_routes,
    export_routes,
    fitting_routes,
    preprocessing_routes,
    recipe_routes,
    spectra_routes,
)
from app.core.constants import SOFTWARE_NAME, SOFTWARE_VERSION
from app.services.spectrum_service import initialize_storage


def _default_cors_origins() -> str:
    origins: list[str] = []
    for port in range(3000, 3011):
        origins.extend([f"http://localhost:{port}", f"http://127.0.0.1:{port}"])
    return ",".join(origins)


app = FastAPI(
    title=SOFTWARE_NAME,
    version=SOFTWARE_VERSION,
    description="Research-grade OES analysis for low-temperature plasma diagnostics.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "PLASMA_SPEC_CORS_ORIGINS",
            _default_cors_origins(),
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spectra_routes.router)
app.include_router(preprocessing_routes.router)
app.include_router(fitting_routes.router)
app.include_router(batch_routes.router)
app.include_router(recipe_routes.router)
app.include_router(export_routes.router)
app.include_router(databases_routes.router)


@app.on_event("startup")
def startup() -> None:
    initialize_storage()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "software": SOFTWARE_NAME, "version": SOFTWARE_VERSION}
