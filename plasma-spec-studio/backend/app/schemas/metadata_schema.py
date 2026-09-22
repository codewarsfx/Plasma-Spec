"""Metadata import schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetadataImportResponse(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    matched_count: int = 0
    unmatched_count: int = 0

