# Pilot 验收报告 — 漫剧 Autopilot M2

**生成时间** : 2026-05-16T16:06:50.832491+00:00
**项目 ID**  : pilot_xiaoyunque_001
**Blueprint SHA** : `42bba513fb011ac4…`
**Plan SHA**      : `fe02917a6abd50af…`
**Style SHA**     : `c5c93fe2a1db68b9…`

## 12 条 Pilot 验收 KPI

总体 : **全部通过 ✅**

| ID | 描述 | 结果 | 数据 |
| --- | --- | --- | --- |
| REQ-PILOT-001 | 3 集端到端 / 0 个 WaitFor | ✅ PASS |  |
| REQ-PILOT-002 | 跨集 ArcFace ≥ 0.92 | ✅ PASS | 1.0 |
| REQ-PILOT-003 | LAION mean ≥ 6.0 / worst ≥ 5.5 | ✅ PASS | [6.566817060940928, 6.569621355362707, 6.282671297259266] |
| REQ-PILOT-004 | VBench Subject ≥ 0.85 | ✅ PASS | [0.9116935933214807, 0.9136914351716254, 0.9206377208318477] |
| REQ-PILOT-005 | UTMOS mean ≥ 4.0 | ✅ PASS | [4.335009823876659, 4.396431407984369, 4.191073964579842] |
| REQ-PILOT-006 | SyncNet 偏移 ≤ 2 帧 | ✅ PASS | 1.0 |
| REQ-PILOT-007 | 单集 ≤ 5 min + ≤ 0 ¥/集 | ✅ PASS | {"runtime_s": 12.57220126666713, "credits": 0} |
| REQ-PILOT-008 | final_report.md 自动生成 | ✅ PASS |  |
| REQ-PILOT-009 | Chaos 注入 5xx 一次仍恢复 | ✅ PASS |  |
| REQ-PILOT-010 | Determinism ≥ 95% | ✅ PASS | 1.0 |
| REQ-PILOT-011 | 0 路径触及禁词（静态 + 运行） | ✅ PASS | {"static_violations": 0, "runtime_violations": 0} |
| REQ-PILOT-012 | Outfit 翻色 bug 1 cycle 内自动修复 | ✅ PASS |  |

## 集级 KPI 详表

| Episode | 状态 | LAION mean | ArcFace mean | VBench mean | UTMOS mean | SyncNet max | Cycles |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ep01 | PROMOTED | 6.567 | 0.998 | 0.912 | 4.335 | 1.0 | 0 |
| ep02 | PROMOTED | 6.570 | 0.998 | 0.914 | 4.396 | 1.0 | 0 |
| ep03 | PROMOTED | 6.283 | 0.998 | 0.921 | 4.191 | 1.0 | 0 |

## 跨集一致性

`continuity` =

```json
{
  "matrix": {
    "ep01|ep02": {
      "char_10782561": {
        "arcface": 1.0
      },
      "char_47985157": {
        "arcface": 1.0
      }
    },
    "ep01|ep03": {
      "char_10782561": {
        "arcface": 1.0
      },
      "char_47985157": {
        "arcface": 1.0
      }
    },
    "ep02|ep03": {
      "char_10782561": {
        "arcface": 1.0
      },
      "char_47985157": {
        "arcface": 1.0
      }
    }
  },
  "drifted": [],
  "compared": [
    "ep01",
    "ep02",
    "ep03"
  ]
}
```

