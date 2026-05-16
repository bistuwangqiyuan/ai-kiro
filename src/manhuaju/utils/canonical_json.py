"""Canonical-JSON serialiser + sha256 helper.

Backs REQ-SA-010 / REQ-CB-006 / REQ-VS-005 / REQ-NFR-PROV-002 (deterministic
artefact fingerprints). Two equal logical objects must serialise to the
*exact same bytes* across platforms and Python versions.

Rules:
- keys sorted lexicographically at every depth
- separators `(", ", ": ")` removed -> `(",", ":")` (no whitespace)
- ensure_ascii=False (UTF-8) so Chinese characters are stable
- floats formatted via repr to keep round-trip stability
- pydantic BaseModel instances are dumped via `model_dump(mode='json')`
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover - pydantic always installed in this project
    BaseModel = object  # type: ignore[misc,assignment]


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "__str__"):
        return str(obj)
    return obj


def to_canonical(obj: Any) -> str:
    """Return canonical JSON string."""
    jsonable = _to_jsonable(obj)
    return json.dumps(
        jsonable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_of(obj: Any) -> str:
    """sha256 hex digest of the canonical JSON."""
    return hashlib.sha256(to_canonical(obj).encode("utf-8")).hexdigest()
