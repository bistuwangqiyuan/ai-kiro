"""IterationManagerAgent — failure-mode + VLM-driven repair loop.

v4 升级 ★：
- 接受 Doubao Seed 1.6 VLM 输出的 ``issues`` 列表（face_drift / axis_violation /
  limb_distortion / text_garbled / style_offshift / intent_mismatch / detail_loss /
  color_drift），按 ``V4_REPAIR_ROUTES`` 路由到合适的 repair adapter。
- 保留原 F-001..F-030 failure-mode 决策表 + retry budget 守门。
- 输出统一 plans 数组：每条带 ``adapter_kind``（xiaoyunque / seedance / wanflf /
  overlay / discard）+ ``hint`` 文本指引。

实现 docx 十二节「自动修正」闭环：生成→评估→修正→再评估，最多 3 cycle。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.failure_modes import RETRY_BUDGETS, TABLE, repair_route_for
from manhuaju.schemas import FailureMode


@dataclass
class RepairPlan:
    failure_mode: FailureMode | None
    target: str
    target_id: str
    strategy: str
    adapter_kind: str = "xiaoyunque"
    hint: str = ""
    issue_type: str | None = None
    severity: str = "medium"
    extra: dict[str, Any] = field(default_factory=dict)


class IterationManagerAgent(BaseAgent):
    name = "IterationManagerAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        shot_reports: list[dict[str, Any]] = req.inputs.get("shot_reports", []) or []
        drifted: list[str] = req.inputs.get("drifted", []) or []
        vlm_reports: list[dict[str, Any]] = req.inputs.get("vlm_reports", []) or []

        plans: list[RepairPlan] = []

        # ---- 1) 旧 F-### 决策表 ----
        plans.extend(self._from_shot_reports(shot_reports))
        plans.extend(self._from_drifted(drifted))

        # ---- 2) v4 VLM issue 路由 ----
        plans.extend(self._from_vlm_reports(vlm_reports))

        # ---- 3) 限流 ----
        capped = self._apply_budget(plans)

        return AgentRunResponse(
            status="succeeded",
            outputs={
                "plans": [self._serialise(p) for p in capped],
                "total_raw": len(plans),
                "total_capped": len(capped),
            },
            metrics={
                "plans": float(len(capped)),
                "vlm_routes": float(sum(1 for p in capped if p.issue_type)),
            },
        )

    # ----- helpers -----
    def _from_shot_reports(self, shot_reports: list[dict[str, Any]]) -> list[RepairPlan]:
        out: list[RepairPlan] = []
        for s in shot_reports:
            if s.get("verdict") == "pass":
                continue
            for reason in s.get("reasons", []):
                fm_id = reason.split(":", 1)[0]
                try:
                    fm = FailureMode(fm_id)
                except ValueError:
                    continue
                strat = TABLE[fm]
                out.append(
                    RepairPlan(
                        failure_mode=fm,
                        target=strat.target,
                        target_id=s.get("shot_id", "unknown"),
                        strategy=strat.name,
                        adapter_kind="xiaoyunque",
                    )
                )
        return out

    def _from_drifted(self, drifted: list[str]) -> list[RepairPlan]:
        out: list[RepairPlan] = []
        for char_id in drifted:
            out.append(
                RepairPlan(
                    failure_mode=FailureMode.F003_CONSISTENCY_FACE_LOW,
                    target="char_refs",
                    target_id=char_id,
                    strategy=TABLE[FailureMode.F003_CONSISTENCY_FACE_LOW].name,
                    adapter_kind="wanflf",
                    hint="跨集 ArcFace 低于 0.78：触发 FLF 重生",
                )
            )
        return out

    def _from_vlm_reports(self, vlm_reports: list[dict[str, Any]]) -> list[RepairPlan]:
        out: list[RepairPlan] = []
        for r in vlm_reports:
            shot_id = r.get("shot_id", "unknown")
            for issue in r.get("issues", []):
                itype = str(issue.get("type", "")).lower()
                if not itype:
                    continue
                severity = str(issue.get("severity", "medium"))
                adapter_kind, hint = repair_route_for(itype)
                # Map VLM issue → FailureMode for traceability
                fm = _vlm_issue_to_failure_mode(itype)
                strat = TABLE[fm].name if fm else "vlm_repair"
                out.append(
                    RepairPlan(
                        failure_mode=fm,
                        target=("shot" if adapter_kind != "overlay" else "episode"),
                        target_id=shot_id,
                        strategy=strat,
                        adapter_kind=adapter_kind,
                        hint=hint,
                        issue_type=itype,
                        severity=severity,
                        extra={
                            "frame": issue.get("frame"),
                            "bbox": issue.get("bbox"),
                            "confidence": issue.get("confidence"),
                            "vlm_scores": r.get("scores"),
                            "verdict": r.get("verdict"),
                        },
                    )
                )
        return out

    def _apply_budget(self, plans: list[RepairPlan]) -> list[RepairPlan]:
        seen: dict[str, int] = {}
        capped: list[RepairPlan] = []
        for p in plans:
            key = f"{p.target}:{p.target_id}"
            cap = RETRY_BUDGETS.get(p.target, 1)
            n = seen.get(key, 0)
            if n < cap:
                capped.append(p)
                seen[key] = n + 1
        return capped

    @staticmethod
    def _serialise(p: RepairPlan) -> dict[str, Any]:
        return {
            "failure_mode": p.failure_mode.value if p.failure_mode else None,
            "target": p.target,
            "target_id": p.target_id,
            "strategy": p.strategy,
            "adapter_kind": p.adapter_kind,
            "hint": p.hint,
            "issue_type": p.issue_type,
            "severity": p.severity,
            "extra": p.extra,
        }


def _vlm_issue_to_failure_mode(itype: str) -> FailureMode | None:
    mapping: dict[str, FailureMode] = {
        "face_drift": FailureMode.F003_CONSISTENCY_FACE_LOW,
        "axis_violation": FailureMode.F022_INTENT_MISMATCH,
        "limb_distortion": FailureMode.F021_SEVEN_DIM_FAIL,
        "text_garbled": FailureMode.F019_MIME_MISMATCH,
        "style_offshift": FailureMode.F023_STYLE_DRIFT,
        "intent_mismatch": FailureMode.F022_INTENT_MISMATCH,
        "detail_loss": FailureMode.F021_SEVEN_DIM_FAIL,
        "color_drift": FailureMode.F023_STYLE_DRIFT,
    }
    return mapping.get(itype)
