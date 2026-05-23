"""Single-shot worker — pull AT MOST ``MANHUAJU_BURST_JOBS`` jobs and exit.

设计目的：作为 VeFaaS 定时触发函数 / 消息触发函数的 entrypoint。
和 ``run_worker.py`` 的区别：

- ``run_worker.py``  : 长轮询常驻进程（ECS / K8s 用）
- ``run_worker_once.py``: 跑一轮（最多 N 个任务）就退出（serverless 用）

环境变量：
- ``MANHUAJU_BURST_JOBS``    : 单次最多拉几个任务（默认 1）
- ``MANHUAJU_BURST_BUDGET_S``: 总预算秒数（默认 1500 = 25min）；接近耗尽时立即退出
- ``MANHUAJU_API_DATA``      : 数据根目录（VeFaaS 一般挂 NAS 到 /data）
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def _exit_payload(payload: dict[str, Any], rc: int = 0) -> int:
    """Print VeFaaS function response (JSON) and return rc."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    return rc


def handler(event: Any = None, context: Any = None) -> dict[str, Any]:
    """VeFaaS 容器函数 / 消息函数 handler。

    返回字典；同时也会作为 JSON 打到 stdout 方便 CLI 调试。
    """
    from manhuaju.api.app import create_app

    data_root = Path(os.getenv("MANHUAJU_API_DATA", "./api_data"))
    burst = int(os.getenv("MANHUAJU_BURST_JOBS", "1"))
    budget_s = float(os.getenv("MANHUAJU_BURST_BUDGET_S", "1500"))

    started = time.time()
    app = create_app(storage_root=data_root)
    batch = app.state.batch_scheduler
    ran_ids: list[str] = []
    errors: list[str] = []

    for i in range(max(1, burst)):
        if time.time() - started > budget_s:
            break
        try:
            jid = batch.run_next()
            if jid is None:
                # 队列空，提早退出
                break
            ran_ids.append(jid)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")
            # 一个任务挂掉不影响后续 burst
            continue

    try:
        batch.shutdown()
    except Exception:  # noqa: BLE001
        pass

    return {
        "ran": ran_ids,
        "count": len(ran_ids),
        "elapsed_s": round(time.time() - started, 2),
        "errors": errors,
        "ok": len(errors) == 0,
        "event": str(event)[:200] if event else None,
    }


def main() -> int:
    out = handler()
    return _exit_payload(out, rc=0 if out["ok"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
