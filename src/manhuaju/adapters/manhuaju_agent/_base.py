"""Shared infrastructure for the 火山「短剧漫剧 Agent」4-step pipeline.

每一步都是两阶段异步任务（``CVSync2AsyncSubmitTask`` → ``CVSync2AsyncGetResult``），
共享：

- 火山 Visual V4 签名 — 直接复用 ``volcengine.visual.VisualService.VisualService``
  （已在 :class:`manhuaju.adapters.render.real_xiaoyunque_adapter.RealXiaoyunqueAdapter`
  中验证可用）。
- 任务提交 + 轮询封装 :func:`ManhuajuAgentBase.submit_and_poll`。
- 错误分类（可重试 vs 不可重试）。
- 成本/延迟埋点 via :class:`manhuaju.core.cost_tracker.CostTracker`。

错误码（来源火山官方文档 [docs/85621/2459788](https://www.volcengine.com/docs/85621/2459788?lang=zh)）：

| Code | 含义 | 是否可重试 |
|------|------|------------|
| 10000 | 成功 | — |
| 50411/50511 | 图片审核未通过 | 否（业务侧需修改输入） |
| 50412/50512/50413 | 文本审核未通过 | 否 |
| 50429/50430 | 限流 | 是（指数退避） |
| 50500 | 内部错误 | 是（最多 3 次） |
| not_found / expired | 任务过期（>12h） | 否 |
"""

from __future__ import annotations

import contextlib
import json
import random
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, TypeVar

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

T = TypeVar("T")


class BusinessErrorCode(IntEnum):
    """火山「短剧漫剧 Agent」业务错误码（覆盖文档列出的全部）。"""

    SUCCESS = 10000
    IMAGE_AUDIT_FAILED_A = 50411
    IMAGE_AUDIT_FAILED_B = 50511
    TEXT_AUDIT_FAILED_A = 50412
    TEXT_AUDIT_FAILED_B = 50512
    TEXT_AUDIT_FAILED_C = 50413
    RATE_LIMIT_A = 50429
    RATE_LIMIT_B = 50430
    INTERNAL_ERROR = 50500

    @property
    def is_retryable(self) -> bool:
        return self in {
            BusinessErrorCode.RATE_LIMIT_A,
            BusinessErrorCode.RATE_LIMIT_B,
            BusinessErrorCode.INTERNAL_ERROR,
        }


_TASK_STATE_FINAL_SUCCESS = "done"
_TASK_STATE_FINAL_FAILURE = {"failed", "expired", "not_found"}


class ManhuajuAgentError(RuntimeError):
    """业务级错误（非重试或重试用尽）。"""

    def __init__(self, code: int, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.payload = payload or {}

    @property
    def is_audit(self) -> bool:
        return self.code in {50411, 50511, 50412, 50512, 50413}


class PollTimeoutError(ManhuajuAgentError):
    """轮询超过 ``max_poll_s`` 仍未完成。"""

    def __init__(self, task_id: str, elapsed: float, max_poll: float) -> None:
        super().__init__(
            code=-1,
            message=f"task {task_id} did not finish in {elapsed:.0f}s (limit={max_poll:.0f}s)",
            payload={"task_id": task_id, "elapsed_s": elapsed, "max_poll_s": max_poll},
        )


@dataclass(frozen=True)
class TaskHandle:
    """任务句柄：``submit`` 阶段产出，``poll`` 阶段消费。"""

    task_id: str
    req_key: str
    business: str  # script_analysis / material_design / video_generate / video_compose
    extra: dict[str, Any]


class ManhuajuAgentBase:
    """4 个适配器的公共父类，封装签名 + 两阶段轮询 + 错误处理。"""

    name: str = "ManhuajuAgentBase"
    provider: str = "volcengine_manhuaju_agent"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.mock_fallback = mock_fallback
        self._poll_interval_s = float(self._cfg.get("poll_interval_s", 10))
        self._max_poll_s = float(self._cfg.get("max_poll_s", 2400))
        self._max_retries = int(self._cfg.get("max_retries", 3))
        self._svc: Any | None = None
        self._init_visual_sdk()

    # ----- SDK init -----
    def _init_visual_sdk(self) -> None:
        if not self._settings.has_xiaoyunque:
            return
        try:
            from volcengine.visual.VisualService import (  # type: ignore[import-untyped]
                VisualService,
            )
        except ImportError:
            self._svc = None
            return

        self._svc = VisualService()
        self._svc.set_ak(self._settings.volcengine_visual_ak)
        self._svc.set_sk(self._settings.volcengine_visual_sk)
        with contextlib.suppress(AttributeError):
            self._svc.set_region(self._settings.volcengine_visual_region)

    @property
    def is_live(self) -> bool:
        return self._svc is not None and self._settings.has_xiaoyunque

    # ----- helpers -----
    @staticmethod
    def gen_run_id(prefix: str = "run") -> str:
        """生成 ≤32 字符的 ``run_id``，满足火山官方限制。"""
        body = uuid.uuid4().hex[:24]
        # final size ≤ 32: prefix '_' + 24 hex
        max_prefix = 32 - 1 - 24
        p = (prefix or "run")[:max_prefix]
        return f"{p}_{body}"[:32]

    # ----- core submit & poll -----
    def submit_and_poll(
        self,
        *,
        business: str,
        req_key: str,
        submit_body: dict[str, Any],
        result_parser: Callable[[dict[str, Any]], T],
        poll_interval_s: float | None = None,
        max_poll_s: float | None = None,
        operation_tag: str = "manhuaju",
    ) -> T:
        """提交任务并轮询至成功/失败，返回 ``result_parser`` 解析后的对象。

        Args:
            business: 业务名（埋点用），如 ``"script_analysis"``。
            req_key: 火山接口 ``req_key`` 常量。
            submit_body: 除 ``req_key`` 外的提交字段。
            result_parser: ``resp_data`` (已 ``json.loads``) → 业务模型。
            poll_interval_s / max_poll_s: 覆盖默认值。
            operation_tag: ``cost`` 埋点 operation 名。

        Raises:
            ManhuajuAgentError: 业务错误码、提交失败、解析失败。
            PollTimeoutError: 轮询超时。
        """
        if not self.is_live or self._svc is None:
            raise ManhuajuAgentError(
                code=-1,
                message="VisualService SDK not configured (need VOLCENGINE_VISUAL_AK/SK)",
            )

        handle = self._submit(business, req_key, submit_body, operation_tag)
        return self._poll(
            handle,
            result_parser,
            poll_interval_s or self._poll_interval_s,
            max_poll_s or self._max_poll_s,
            operation_tag,
        )

    # ----- submit -----
    def _submit(
        self,
        business: str,
        req_key: str,
        submit_body: dict[str, Any],
        operation_tag: str,
    ) -> TaskHandle:
        params = {"req_key": req_key, **{k: v for k, v in submit_body.items() if v not in (None, "")}}

        attempt = 0
        while True:
            attempt += 1
            t0 = now_s()
            try:
                resp = self._svc.cv_sync2async_submit_task(params)  # type: ignore[union-attr]
                duration = now_s() - t0
            except Exception as e:  # noqa: BLE001
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider=self.provider,
                        operation=f"{operation_tag}.submit",
                        model=req_key,
                        duration_s=now_s() - t0,
                        success=False,
                        error_class=type(e).__name__,
                        extra={"business": business, "attempt": attempt},
                    )
                )
                if attempt > self._max_retries:
                    raise ManhuajuAgentError(
                        code=-1,
                        message=f"submit transport error: {e}",
                        payload={"business": business, "req_key": req_key},
                    ) from e
                self._sleep_backoff(attempt)
                continue

            task_id = self._extract_task_id(resp, req_key, business)
            code, message = self._extract_code(resp)
            success = code == BusinessErrorCode.SUCCESS

            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation=f"{operation_tag}.submit",
                    model=req_key,
                    duration_s=duration,
                    success=success,
                    error_class=None if success else f"code={code}",
                    extra={"business": business, "task_id": task_id, "attempt": attempt},
                )
            )

            if not success:
                if self._is_retryable_code(code) and attempt <= self._max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise ManhuajuAgentError(code=code, message=message, payload={"resp": resp})

            if not task_id:
                raise ManhuajuAgentError(
                    code=-1,
                    message="submit succeeded but task_id missing",
                    payload={"resp": resp},
                )

            return TaskHandle(
                task_id=task_id,
                req_key=req_key,
                business=business,
                extra={"submit_body": submit_body},
            )

    # ----- poll -----
    def _poll(
        self,
        handle: TaskHandle,
        result_parser: Callable[[dict[str, Any]], T],
        poll_interval_s: float,
        max_poll_s: float,
        operation_tag: str,
    ) -> T:
        deadline = time.time() + max_poll_s
        consecutive_errors = 0
        last_resp: dict[str, Any] | None = None

        while time.time() < deadline:
            t0 = now_s()
            try:
                resp = self._svc.cv_sync2async_get_result(  # type: ignore[union-attr]
                    {"req_key": handle.req_key, "task_id": handle.task_id}
                )
                duration = now_s() - t0
            except Exception as e:  # noqa: BLE001
                consecutive_errors += 1
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider=self.provider,
                        operation=f"{operation_tag}.poll",
                        model=handle.req_key,
                        duration_s=now_s() - t0,
                        success=False,
                        error_class=type(e).__name__,
                        extra={"business": handle.business, "task_id": handle.task_id},
                    )
                )
                if consecutive_errors > self._max_retries:
                    raise ManhuajuAgentError(
                        code=-1,
                        message=f"poll transport error: {e}",
                        payload={"task_id": handle.task_id},
                    ) from e
                self._sleep_backoff(consecutive_errors)
                continue
            consecutive_errors = 0
            last_resp = resp

            code, message = self._extract_code(resp)
            status = self._extract_status(resp)

            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation=f"{operation_tag}.poll",
                    model=handle.req_key,
                    duration_s=duration,
                    success=code == BusinessErrorCode.SUCCESS,
                    error_class=None if code == BusinessErrorCode.SUCCESS else f"code={code}",
                    extra={
                        "business": handle.business,
                        "task_id": handle.task_id,
                        "status": status,
                    },
                )
            )

            if code != BusinessErrorCode.SUCCESS:
                if self._is_retryable_code(code):
                    time.sleep(poll_interval_s)
                    continue
                raise ManhuajuAgentError(code=code, message=message, payload={"resp": resp})

            if status in _TASK_STATE_FINAL_FAILURE:
                raise ManhuajuAgentError(
                    code=-1,
                    message=f"task {handle.task_id} ended with status={status}",
                    payload={"resp": resp},
                )

            if status == _TASK_STATE_FINAL_SUCCESS:
                resp_data = self._extract_resp_data(resp)
                if resp_data is None:
                    raise ManhuajuAgentError(
                        code=-1,
                        message="task done but resp_data missing",
                        payload={"resp": resp},
                    )
                try:
                    return result_parser(resp_data)
                except Exception as e:  # noqa: BLE001
                    raise ManhuajuAgentError(
                        code=-1,
                        message=f"resp_data parse failed: {e}",
                        payload={"resp_data": resp_data},
                    ) from e

            time.sleep(poll_interval_s)

        raise PollTimeoutError(handle.task_id, max_poll_s, max_poll_s)

    # ----- response decoders -----
    @staticmethod
    def _extract_task_id(resp: Any, req_key: str, business: str) -> str:  # noqa: ARG004
        if not isinstance(resp, dict):
            return ""
        data = resp.get("data") or {}
        return str(data.get("task_id") or data.get("TaskID") or "")

    @staticmethod
    def _extract_code(resp: Any) -> tuple[int, str]:
        if not isinstance(resp, dict):
            return -1, "non-dict response"
        code_raw = resp.get("code", resp.get("status"))
        try:
            code = int(code_raw) if code_raw is not None else -1
        except (TypeError, ValueError):
            code = -1
        msg = str(resp.get("message") or resp.get("Message") or "")
        return code, msg

    @staticmethod
    def _extract_status(resp: Any) -> str:
        if not isinstance(resp, dict):
            return ""
        data = resp.get("data") or {}
        return str(data.get("status") or data.get("Status") or "").lower()

    @staticmethod
    def _extract_resp_data(resp: Any) -> dict[str, Any] | None:
        """``resp.data.resp_data`` is itself JSON-encoded string."""
        if not isinstance(resp, dict):
            return None
        data = resp.get("data") or {}
        raw = data.get("resp_data")
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _is_retryable_code(code: int) -> bool:
        try:
            return BusinessErrorCode(code).is_retryable
        except ValueError:
            return False

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        # exponential backoff with jitter; capped at 30s
        base = min(2 ** attempt, 30)
        time.sleep(base + random.uniform(0, 1))
