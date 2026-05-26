"""Real Seedream 4 style-transfer adapter (production path).

Lazy imports the Volcengine VisualGenerate / Seedream client. If credentials
or the SDK are missing, raises ``RuntimeError`` so the orchestrator can
fall back to ``mock_adapter``.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from manhuaju.adapters.styletransfer.mock_adapter import StyleTransferResult


def _load_client() -> Any:
    try:
        return importlib.import_module("volcengine.visual.VisualService")
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("volcengine SDK not installed") from exc


def _require_credentials() -> tuple[str, str]:
    ak = os.environ.get("VOLC_ACCESSKEY") or os.environ.get("MANHUAJU_VOLC_AK")
    sk = os.environ.get("VOLC_SECRETKEY") or os.environ.get("MANHUAJU_VOLC_SK")
    if not ak or not sk:
        raise RuntimeError(
            "Volcengine credentials missing (VOLC_ACCESSKEY/VOLC_SECRETKEY); "
            "use mock_adapter for offline runs."
        )
    return ak, sk


def transfer(
    input_path: str,
    target_style: str,
    identity_lock: bool = True,
    output_path: str | None = None,
) -> StyleTransferResult:
    """Run Seedream style transfer; raises ``RuntimeError`` when prerequisites missing."""

    _require_credentials()
    _load_client()
    raise RuntimeError(
        "Seedream style transfer not implemented in v2.0 mock build; "
        f"input={input_path}, target_style={target_style}, identity_lock={identity_lock}, "
        f"output={output_path}"
    )
