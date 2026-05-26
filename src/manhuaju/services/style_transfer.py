"""Style-transfer orchestrator (REQ-STR-001..006).

Allowed target styles: ``j_anime``, ``c_anime``, ``realistic``, ``2d``.
Identity lock is enforced via an ArcFace gate (``≥ 0.94`` by default).

The service is *adapter-agnostic*: callers pass any callable matching
``transfer(input_path, target_style, identity_lock, output_path) -> StyleTransferResult``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from manhuaju.adapters.styletransfer.mock_adapter import StyleTransferResult, transfer

#: REQ-STR-002: ArcFace identity-lock threshold (whitepaper anchor).
IDENTITY_GATE = 0.94

TargetStyle = Literal["j_anime", "c_anime", "realistic", "2d"]
ALL_STYLES: tuple[TargetStyle, ...] = ("j_anime", "c_anime", "realistic", "2d")

TransferFn = Callable[[str, str, bool, str | None], StyleTransferResult]


@dataclass
class StyleTransferSvc:
    transfer_fn: TransferFn = field(default=transfer)
    log: list[StyleTransferResult] = field(default_factory=list)

    def list_targets(self) -> tuple[TargetStyle, ...]:
        return ALL_STYLES

    def transfer_with_gate(
        self,
        input_path: str,
        target_style: TargetStyle,
        *,
        identity_lock: bool = True,
        gate: float = IDENTITY_GATE,
        retries: int = 1,
    ) -> tuple[StyleTransferResult, bool]:
        """REQ-STR-002 + -003: run style transfer + identity gate.

        Returns ``(result, passed)`` where ``passed`` is ``True`` only when the
        ArcFace score is at or above the gate. The function may retry up to
        ``retries`` times if the gate fails (each retry uses a perturbed seed
        via the output path suffix).
        """

        if target_style not in ALL_STYLES:
            raise ValueError(f"unsupported target_style: {target_style!r}")
        last: StyleTransferResult | None = None
        for attempt in range(retries + 1):
            out_path = f"{input_path}.{target_style}.try{attempt}.png"
            res = self.transfer_fn(input_path, target_style, identity_lock, out_path)
            self.log.append(res)
            last = res
            if res.arcface_score >= gate:
                return res, True
        assert last is not None
        return last, False

    def batch_apply(
        self,
        inputs: list[str],
        target_style: TargetStyle,
        *,
        identity_lock: bool = True,
    ) -> list[tuple[StyleTransferResult, bool]]:
        """REQ-STR-004: apply same style to multiple frames; report per-frame pass/fail."""

        return [self.transfer_with_gate(p, target_style, identity_lock=identity_lock) for p in inputs]

    def pass_rate(self) -> float:
        if not self.log:
            return 0.0
        passed = sum(1 for r in self.log if r.arcface_score >= IDENTITY_GATE)
        return passed / len(self.log)
