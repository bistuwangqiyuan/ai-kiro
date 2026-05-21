# 漫剧 Autopilot — 六步商业工作流补充需求 (v2)

> 本文件补充 [requirements.md](requirements.md)，映射 [流程和需求.docx](../../../流程和需求.docx) 的六步工作流、7 维 QA、分发与可选 supervised 模式。
> 与 P-1 Autopilot 并存：`workflow.mode=autopilot` 为默认；`supervised` 仅在 Step 6 启用 ReviewGate。

---

## 23. 六步工作流 (REQ-WF-***)

| REQ-ID | EARS 摘要 |
| --- | --- |
| REQ-WF-001 | **WHEN** 项目进入生产，**THE SYSTEM SHALL** 将管线划分为 6 个显式阶段：analyze / assets / prompts / draw / rough_cut / fine_cut，并写入状态日志与 artefact 路径。 |
| REQ-WF-002 | **WHEN** Step 1 analyze 完成，**THE SYSTEM SHALL** 产出 StoryBlueprint + EpisodePlan + 台词优化后的 Script 草稿（DialogueOptimizer）。 |
| REQ-WF-003 | **WHEN** Step 2 assets 完成，**THE SYSTEM SHALL** 产出人物/场景/道具参考资产及 `asset_manifest.json`。 |
| REQ-WF-004 | **WHEN** Step 3 prompts 完成，**THE SYSTEM SHALL** 产出 Storyboard + 每镜头 `prompt_brief.clauses` ≥ 10。 |
| REQ-WF-005 | **WHEN** Step 4 draw 完成，**THE SYSTEM SHALL** 支持每镜头 N 候选抽卡并自动择优；参考图 URI 注入 i2v submit payload。 |
| REQ-WF-006 | **WHEN** Step 5–6 完成，**THE SYSTEM SHALL** 先粗剪（拼接+粗对齐音轨），再精剪（逐句字幕、loudnorm、转场、SFX），最后接 QA 闭环。 |

---

## 24. 七维 QA (REQ-QA7-***)

| REQ-ID | 维度 | 阈值 (0–10) |
| --- | --- | --- |
| REQ-QA7-001 | 结构正确性 | ≥ 7.0 |
| REQ-QA7-002 | 风格一致性 | ≥ 7.0 |
| REQ-QA7-003 | 细节完整性 | ≥ 7.0 |
| REQ-QA7-004 | 画质清晰度 | ≥ 7.0 |
| REQ-QA7-005 | 色彩协调性 | ≥ 7.0 |
| REQ-QA7-006 | 无崩坏（脸/手/肢体） | ≥ 7.0 |
| REQ-QA7-007 | 意图匹配度（prompt vs 帧） | ≥ 7.0 |

---

## 25. 分发导出 (REQ-DIST-***)

| REQ-ID | EARS 摘要 |
| --- | --- |
| REQ-DIST-001 | **WHEN** 单集精剪通过 QA，**THE SYSTEM SHALL** 按平台 preset（抖音/快手/视频号）转码 9:16 MP4。 |
| REQ-DIST-002 | **THE SYSTEM SHALL** 从首帧 + LLM 标题生成封面 PNG。 |
| REQ-DIST-003 | **IF** `distribution.watermark` 启用，**THE SYSTEM SHALL** ffmpeg overlay 账号水印。 |
| REQ-DIST-004 | **THE SYSTEM SHALL** 产出 `copy_pack.json`（标题/简介/引流话术）。 |

---

## 26. 运行模式 (REQ-MODE-***)

| REQ-ID | EARS 摘要 |
| --- | --- |
| REQ-MODE-supervised | **IF** `workflow.mode=supervised`，**WHEN** Step 6 完成且 QA 通过，**THE SYSTEM SHALL** 进入 `AwaitingReview` 直至 API `approve/reject/partial_rerender`；**autopilot 默认不触发**。 |
| REQ-MODE-autopilot | **WHEN** `workflow.mode=autopilot`（默认），**THE SYSTEM SHALL** 保持 0 人工节点，与 REQ-MO-008 / REQ-PILOT-011 一致。 |

---

## 27. 平台 API (REQ-API-***)

| REQ-ID | EARS 摘要 |
| --- | --- |
| REQ-API-001 | **THE SYSTEM SHALL** 暴露 FastAPI `/v1/projects` CRUD + 6 步进度查询。 |
| REQ-API-002 | **THE SYSTEM SHALL** 支持 BackgroundTasks + SQLite job queue 执行长任务。 |
| REQ-API-003 | **WHEN** supervised，`POST /v1/projects/{id}/review/{ep}` 接受 approve/reject/partial_rerender。 |
| REQ-API-004 | **THE SYSTEM SHALL** 提供 `/health` 与 Docker/Railway 部署清单。 |

---

## 28. 新增 Agent (REQ-AGENT-v2-***)

| REQ-ID | Agent |
| --- | --- |
| REQ-AGENT-v2-001 | DialogueOptimizerAgent |
| REQ-AGENT-v2-002 | SceneAssetAgent |
| REQ-AGENT-v2-003 | PropAssetAgent |
| REQ-AGENT-v2-004 | DistributionAgent |
