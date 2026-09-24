"""Recursively strip non-finite floats (NaN/Infinity) so a value is always
safe to JSON-encode strictly (``allow_nan=False``).

NaN can enter spectrum metadata from a blank Excel cell or a partial
filename-pattern match, and can enter fit results from a diverged/degenerate
fit. Two things in this app encode strictly and raise on it: Starlette's
default ``JSONResponse`` (``json.dumps(..., allow_nan=False)``, so an
un-sanitized NaN anywhere in an API response 500s the whole request), and
``httpx`` (same ``allow_nan=False``, used internally by ``supabase-py`` for
every table write -- so an un-sanitized NaN in a Supabase upsert fails
before the request is even sent). Apply this at every storage boundary
(local SQLite writes, Supabase writes, outgoing API responses) rather than
track down every possible source of a stray NaN.
"""

from __future__ import annotations

import math
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
