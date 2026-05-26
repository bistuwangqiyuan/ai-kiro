"""Dual-mode entry router for Manhuaju Autopilot v2.0 (REQ-MODE-001..006).

Two coexisting interaction modes — ``simple`` (one-knob) and ``pro`` (full).
The same FastAPI backend serves both; this module only enforces the parameter
contract loaded from ``config/modes.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from manhuaju.utils.paths import config_dir

ModeName = Literal["simple", "pro"]


@dataclass(frozen=True)
class ModePreset:
    name: ModeName
    locked_params: tuple[str, ...]
    defaults: dict[str, Any]
    exposed_params: tuple[str, ...]

    def is_locked(self, param: str) -> bool:
        return param in self.locked_params


@dataclass
class ModeRouter:
    """Loads ``config/modes.yaml`` and routes incoming payloads."""

    presets: dict[ModeName, ModePreset] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Path | None = None) -> ModeRouter:
        path = config_path or (config_dir() / "modes.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        modes = data.get("modes", {})
        presets: dict[ModeName, ModePreset] = {}
        for name in ("simple", "pro"):
            cfg = modes.get(name, {})
            presets[name] = ModePreset(
                name=name,
                locked_params=tuple(cfg.get("locked_params", [])),
                defaults=dict(cfg.get("defaults", {})),
                exposed_params=tuple(cfg.get("exposed_params", [])),
            )
        return cls(presets=presets)

    def route(self, mode: ModeName, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the incoming payload against the chosen mode and apply preset defaults.

        Raises:
            ValueError: if the user attempts to set a locked parameter (REQ-MODE-004).
        """

        if mode not in self.presets:
            raise ValueError(f"unknown mode: {mode!r}")
        preset = self.presets[mode]
        # 1. forbid locked params
        offending = [p for p in payload if preset.is_locked(p) and payload.get(p) is not None]
        if offending:
            raise ValueError(f"mode_locked: cannot override {offending} in '{mode}' mode")
        # 2. apply defaults (only fill missing keys)
        merged = {**preset.defaults, **{k: v for k, v in payload.items() if v is not None}}
        # 3. record which mode resolved which key
        merged["_mode"] = mode
        merged["_mode_resolved_keys"] = sorted(set(merged.keys()) - {"_mode", "_mode_resolved_keys"})
        return merged

    def exposed(self, mode: ModeName) -> tuple[str, ...]:
        return self.presets[mode].exposed_params
