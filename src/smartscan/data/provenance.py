"""Provenance helpers shared by data adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartscan.types import Provenance, sha256_file


def file_provenance(
    *,
    source: str,
    path: str | Path,
    extra: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> Provenance:
    file_path = Path(path)
    digest = sha256_file(file_path) if file_path.is_file() else None
    transformation = dict(extra or {})
    return Provenance(
        source=source,
        source_uri=file_path.name,
        original_file_sha256=digest,
        transformation=transformation,
        notes=list(notes or []),
    )
