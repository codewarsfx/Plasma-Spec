"""Frozen-backend entrypoint for Electron desktop builds."""

from __future__ import annotations

import os

import uvicorn

from app.main import app


def main() -> None:
    host = os.environ.get("PLASMA_SPEC_HOST", "127.0.0.1")
    port = int(os.environ.get("PLASMA_SPEC_PORT", "18765"))
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.environ.get("PLASMA_SPEC_LOG_LEVEL", "info"),
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
