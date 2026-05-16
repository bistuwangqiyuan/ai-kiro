"""final_report.md generator (REQ-PILOT-008)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def render_kpi_table(items: list[dict[str, Any]]) -> str:
    rows = ["| ID | 描述 | 结果 | 数据 |", "| --- | --- | --- | --- |"]
    for it in items:
        verdict = "✅ PASS" if it["pass"] else "❌ FAIL"
        data = ""
        if "value" in it:
            data = str(it["value"])
        elif "values" in it:
            data = json.dumps(it["values"], ensure_ascii=False)
        rows.append(f"| {it['name']} | {it['label']} | {verdict} | {data} |")
    return "\n".join(rows)


def render_episodes_table(eps: list[dict[str, Any]]) -> str:
    rows = [
        "| Episode | 状态 | LAION mean | ArcFace mean | VBench mean | UTMOS mean | SyncNet max | Cycles |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in eps:
        rows.append(
            f"| {e['episode_id']} | {'PROMOTED' if e.get('promoted') else 'QUARANTINED'} | "
            f"{e['aesthetic_mean']:.3f} | {e['arcface_mean']:.3f} | {e['vbench_mean']:.3f} | "
            f"{e['utmos_mean']:.3f} | {e['syncnet_offset_max']:.1f} | {e['cycles']} |"
        )
    return "\n".join(rows)


def write_final_report(
    *,
    out_path: Path,
    pilot: dict[str, Any],
    manifest: dict[str, Any],
    iteration_log_path: Path | None = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iter_log_md = ""
    if iteration_log_path and iteration_log_path.exists():
        iter_log_md = "\n## 迭代日志\n\n" + iteration_log_path.read_text(encoding="utf-8")
    md = f"""# Pilot 验收报告 — 漫剧 Autopilot M2

**生成时间** : {datetime.now(UTC).isoformat()}
**项目 ID**  : {manifest.get('project_id')}
**Blueprint SHA** : `{manifest.get('blueprint_sha', '')[:16]}…`
**Plan SHA**      : `{manifest.get('plan_sha', '')[:16]}…`
**Style SHA**     : `{manifest.get('style_sha', '')[:16]}…`

## 12 条 Pilot 验收 KPI

总体 : {"**全部通过 ✅**" if pilot['all_pass'] else "**仍有未通过项 ❌**"}

{render_kpi_table(pilot['items'])}

## 集级 KPI 详表

{render_episodes_table(manifest['episodes'])}

## 跨集一致性

`continuity` =

```json
{json.dumps(manifest.get('continuity', {}), ensure_ascii=False, indent=2)}
```
{iter_log_md}
"""
    out_path.write_text(md, encoding="utf-8")
    return out_path


def write_kpi_summary_json(out_path: Path, pilot: dict[str, Any], manifest: dict[str, Any]) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"pilot": pilot, "manifest": manifest},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return out_path
