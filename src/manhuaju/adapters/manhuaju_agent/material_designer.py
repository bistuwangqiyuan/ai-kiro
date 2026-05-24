"""Stage 2: 图片/素材设计 — ``pippit_shortplay_cvtob_material_design``.

一次性产出全剧的角色形象 (``character_detail``)、场景图、分镜参考图。
官方接口以 ``assets_id + thread_id + run_id`` 触发，``run_id`` 必须 ≤32 字符。
"""

from __future__ import annotations

from manhuaju.adapters.manhuaju_agent._base import ManhuajuAgentBase
from manhuaju.adapters.manhuaju_agent.schemas import MaterialDesignResult


class MaterialDesignerAdapter(ManhuajuAgentBase):
    name = "ManhuajuAgent.MaterialDesigner"

    DEFAULT_REQ_KEY = "pippit_shortplay_cvtob_material_design"

    def design(
        self,
        *,
        assets_id: str,
        thread_id: str,
        run_id: str | None = None,
        req_key: str | None = None,
    ) -> MaterialDesignResult:
        body = {
            "assets_id": assets_id,
            "thread_id": thread_id,
            "run_id": run_id or self.gen_run_id("md"),
        }
        return self.submit_and_poll(
            business="material_design",
            req_key=req_key or self.DEFAULT_REQ_KEY,
            submit_body=body,
            result_parser=lambda d: MaterialDesignResult.model_validate(d),
            operation_tag="manhuaju.material",
        )
