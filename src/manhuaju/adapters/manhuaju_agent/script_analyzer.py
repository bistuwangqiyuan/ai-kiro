"""Stage 1: 剧本解析 — ``pippit_shortplay_cvtob_script_analysis``.

输入 docx 公网 URL → 输出 ``ScriptAnalysisResult``（含 ``thread_id`` / ``assets_id`` /
角色 / 场景 / 单集资产指针 / 分镜简介）。
"""

from __future__ import annotations

from typing import Any

from manhuaju.adapters.manhuaju_agent._base import ManhuajuAgentBase
from manhuaju.adapters.manhuaju_agent.schemas import ScriptAnalysisResult


class ScriptAnalyzerAdapter(ManhuajuAgentBase):
    name = "ManhuajuAgent.ScriptAnalyzer"

    DEFAULT_REQ_KEY = "pippit_shortplay_cvtob_script_analysis"

    def analyze(
        self,
        *,
        file_url: str,
        visual_style: str = "真人写实, 电影风格, 冷色调,都市女频",
        video_ratio: str = "16:9",
        file_type: str = "docx",
        file_name: str | None = None,
        req_key: str | None = None,
    ) -> ScriptAnalysisResult:
        """提交剧本解析任务并轮询至完成。

        Args:
            file_url: docx 文件公网可下载 URL（TOS 预签名 URL 即可）。
            visual_style: 视觉风格描述。
            video_ratio: 视频比例，``16:9`` / ``9:16`` / ``1:1``。
            file_type: 文件类型，固定 ``docx``。
            file_name: 显示用文件名（默认从 URL 取末段）。
            req_key: 覆盖默认 ``req_key``（用于切换 pro/fast 等变种）。
        """
        body: dict[str, Any] = {
            "visual_style": visual_style,
            "video_ratio": video_ratio,
            "file_url": file_url,
            "file_type": file_type,
            "file_name": file_name or file_url.rsplit("/", 1)[-1] or "script.docx",
        }
        return self.submit_and_poll(
            business="script_analysis",
            req_key=req_key or self.DEFAULT_REQ_KEY,
            submit_body=body,
            result_parser=lambda d: ScriptAnalysisResult.model_validate(d),
            operation_tag="manhuaju.script",
        )
