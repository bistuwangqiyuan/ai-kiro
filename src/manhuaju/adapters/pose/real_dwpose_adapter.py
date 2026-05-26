"""Real DWPose adapter (production path).

Lazy imports ``onnxruntime`` and the DWPose checkpoint. If the dependency or
checkpoint is unavailable the adapter raises ``RuntimeError`` so callers can
fall back to ``mock_openpose_adapter``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from manhuaju.adapters.pose.mock_openpose_adapter import PoseDetection


def _import_or_fail() -> Any:
    try:
        return importlib.import_module("onnxruntime")
    except ImportError as exc:  # pragma: no cover - guarded by test
        raise RuntimeError("onnxruntime not installed; install consistency extras") from exc


def _checkpoint_path() -> Path:
    """Resolve the DWPose ONNX checkpoint or raise."""

    import os

    env_path = os.environ.get("MANHUAJU_DWPOSE_CKPT")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    raise RuntimeError(
        "MANHUAJU_DWPOSE_CKPT env var not set or checkpoint missing; "
        "this adapter is the live path — use mock_openpose_adapter for tests."
    )


def detect(image_path: Path | str, label: str = "default") -> PoseDetection:
    """Run DWPose inference. Raises ``RuntimeError`` if the runtime/CKPT is absent.

    The function intentionally fails fast so the pipeline can fall back via
    the ``IterationManager`` decision table (REQ-ACT-005).
    """

    _import_or_fail()
    ckpt = _checkpoint_path()
    raise RuntimeError(
        "DWPose inference path not implemented in v2.0 mock-only build; "
        f"checkpoint resolved={ckpt}, image={image_path}, label={label}"
    )
