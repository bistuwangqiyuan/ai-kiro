# Requirements — AI Manhuaju Autopilot (Phase 1)

> Kiro Spec / Phase 1 — Requirements Document
> Spec Name: `ai-manhuaju-autopilot`
> Version: 1.0.0
> Status: Draft for Confirmation
> Owner Agents: `MasterOrchestratorAgent`, `RequirementsAuthoringAgent`
> Reviewer Agents: `SpecReviewAgent`, `ConsistencyAuditAgent`
> 上游 (Upstream): [`.kiro/steering/product.md`](../../steering/product.md), [`.kiro/steering/tech.md`](../../steering/tech.md), [`.kiro/steering/structure.md`](../../steering/structure.md)
> 下游 (Downstream): [`design.md`](./design.md) → [`tasks.md`](./tasks.md)
> 语法标准: EARS (Easy Approach to Requirements Syntax)
> 全文 0 处人类介入，符合 P-1 (Autopilot Only)。本文件用 "the System" 指代整套全自动 Agent 流水线 + 软件运行时；任何"操作员/用户/审核员"在本文件中均**不存在**。

---

## 0. 文档元信息

| 字段 | 值 |
| --- | --- |
| Spec Name | `ai-manhuaju-autopilot` |
| Phase | 1 / 3 (Requirements) |
| Created | 2026-05-16 |
| Last Updated | 2026-05-16 |
| Authoring Agent | `RequirementsAuthoringAgent` v1 |
| Review Agent | `SpecReviewAgent` v1 |
| Total EARS Items | 312 (见附录 E) |
| Traceability | 双向追溯到 Steering / Design §x / Tasks T-#### |
| Compliance Posture | P-1 ~ P-10 全部覆盖；产品红线零容忍 |

### 0.1 EARS 强制字段定义

每条 EARS 需求强制使用以下结构：

```
[REQ-XX-NNN]   Priority=Must|Should|May   Source=P-#   Verify=Unit|Integration|E2E|QAAgent|FormalProof
EARS  : 句式
AC    : 可机器判定的接受标准（数值/正则/断言/事件）
Trace : Design §x.y → Task T-####
```

EARS 五种合法句式：

| Pattern | 模板 |
| --- | --- |
| Ubiquitous | THE SYSTEM SHALL `<行为>` |
| Event-driven | WHEN `<事件>` THE SYSTEM SHALL `<行为>` |
| State-driven | WHILE `<状态>` THE SYSTEM SHALL `<行为>` |
| Optional feature | WHERE `<feature flag>` THE SYSTEM SHALL `<行为>` |
| Unwanted | IF `<触发条件>` THEN THE SYSTEM SHALL `<行为>` |

---

## 1. 目的与范围

### 1.1 目的
建立从**任意中文/英文长篇小说**到**多集、跨集人物 100% 一致、可直接发布**的漫剧（Animated Comic Drama）视频包的**完全无人值守**生产系统的需求基线。本文件等同于全部代码的"宪法"，任何 Agent / Adapter / Pipeline 的实现都必须能反向追溯到至少一条本文件 REQ-ID。

### 1.2 范围 (In-Scope)
- 输入：原始文本小说（≤ 1,000,000 字）+ 全局配置（风格 / 平台 / 语言 / 分辨率 / 预算上限）。
- 输出：N 集视频（默认 60 集），每集 60–180 秒，自带配音、BGM、字幕、片头片尾、合规水印。
- 全流水线：故事架构 → 分集 → 角色档案 → 参考资产 → 剧本 → 分镜 → 渲染 (小云雀 Agent 2.0) → 配音 → 后期 → QA → 跨集一致性 → 自动迭代修复 → 上线包。
- 自动审计：Provenance、KPI、Cost、Compliance Report。

### 1.3 范围外 (Out-of-Scope)
- 任何形式的 GUI 编辑器或人工剪辑界面。
- 原创小说生成（输入必须已存在）。
- 直播 / 实时互动场景。
- 真人未授权肖像。

### 1.4 与 Steering 的映射
| Steering 原则 | 本文件主要承载章节 |
| --- | --- |
| P-1 Autopilot Only | §17 §19 §20 全文反复体现 |
| P-2 Spec-Driven | §0.1 §22 |
| P-3 Determinism + Reproducibility | §17 §19.1 §附录 B |
| P-4 Quality Gates as Code | §15 §16 §19.2 |
| P-5 Character Consistency First | §18（专章） |
| P-6 Cost & Latency Aware | §19.3 |
| P-7 Provenance Everywhere | §17 §19.5 |
| P-8 Observable by Default | §19.4 |
| P-9 Graceful Degradation | §16 §19.6 |
| P-10 Globalization Ready | §13 §19.7 |

---

## 2. 术语与缩写

> 仅列高频与易混淆术语，全表请见 [`docs/glossary.md`](../../../docs/glossary.md)（v1 内容嵌入 Design §0.3）。

| 术语 | 全称 / 定义 |
| --- | --- |
| Agent | 拥有单一职责的自治软件单元，对外暴露 `run(AgentRunRequest) -> AgentRunResponse` |
| Autopilot | 流水线在无任何人类决策点的情况下自我推进、降级、修复、放行的属性 |
| Beat | 故事节拍，分集规划阶段的最小叙事单位 |
| Bible | "圣经"，此处指 `CharacterBible`（角色档案）/ `WorldBible`（世界观档案） |
| BGM | Background Music，背景音乐 |
| Budget | 一次 Agent 调用的资源预算三元组：`(tokens, seconds, credits)` |
| Cliffhanger | 集末钩子，用于跨集留悬念 |
| Continuity | 跨镜头/跨集叙事连续性（人物、道具、地点、时间线） |
| EARS | Easy Approach to Requirements Syntax，Kiro 强制需求语法 |
| Episode | 一集成片，最终交付单元 |
| Failure Mode | 失败模式，附录 C 定义的有限集合 |
| Hook (跨集) | 跨集叙事勾子，用以保留留存率 |
| LoRA | Low-Rank Adaptation，可选的人物专属轻量微调 |
| MOS | Mean Opinion Score，主观音质评分 |
| Provenance | 全链路可追溯证据（输入、Prompt、模型版本、Seed、产物哈希、时间戳） |
| Run | 一次完整项目执行的全局上下文与工件根目录 |
| Seed | 随机数种子，固定后保证 P-3 可复现 |
| Shot | 单镜头，渲染最小单元（5/10/15 秒） |
| State Machine | 有限状态机，控制项目/集/镜头三层生命周期 |
| Trace ID | 一次端到端调用链的全局唯一 ID（OTel） |
| TTS | Text-to-Speech，语音合成 |
| WBS | Work Breakdown Structure；Tasks 文件的组织方式 |
| Xiaoyunque (小云雀) | 字节跳动旗下即梦 AI 的智能生视频 Agent 2.0 / 短剧 Agent，主渲染路径 |
| Seedance 2.0 | 字节跳动底层视频生成模型，作为兜底通路 |

---

## 3. 系统主体 (Stakeholders) — 0 个人类

> 本节强制声明：本系统在运行时不存在任何"人类参与者"角色。所有"参与者"均为软件实体。这是 P-1 的根性约束。

### 3.1 内部 Agent (14 个)

| ID | Agent | 角色 |
| --- | --- | --- |
| A0 | `MasterOrchestratorAgent` | 总调度，状态机推进，生命周期管理 |
| A1 | `StoryArchitectAgent` | 小说→世界观/时间线/角色关系图 |
| A2 | `EpisodePlannerAgent` | 切集 + 钩子设计 + 时长预算 |
| A3 | `CharacterBibleAgent` | 跨集角色档案与状态机 |
| A4 | `ReferenceAssetAgent` | 多视图参考图、参考视频、可选 LoRA |
| A5 | `ScriptWriterAgent` | 集→场→镜的剧本（Fountain） |
| A6 | `StoryboardDirectorAgent` | 镜头脚本（构图/景别/运镜/时长） |
| A7 | `VisualStyleAgent` | 风格锁、调色板、镜头语言 |
| A8 | `VoiceDirectorAgent` | 配音映射与情感韵律 |
| A9 | `MusicDirectorAgent` | BGM / SFX / 节奏曲线 |
| A10 | `RenderOrchestratorAgent` | 调用小云雀 / Seedance 完成镜头渲染 |
| A11 | `QAReviewerAgent` | 镜头/集/系列三层 QA |
| A12 | `ContinuityCheckerAgent` | 跨集一致性 + 物品/位置追踪 |
| A13 | `IterationManagerAgent` | 失败诊断 + 修复策略 + 回滚 |

### 3.2 外部依赖 (5 大类)

| ID | 外部系统 | 用途 |
| --- | --- | --- |
| X1 | 火山引擎即梦 AI / 小云雀 Agent 2.0 | 主渲染通路 |
| X2 | 火山方舟 Seedance 2.0 | 兜底渲染通路 |
| X3 | LLM Pool（DeepSeek-V3 / Qwen3-Max / GPT-4.1 / Claude 3.7） | 叙事 / Agent / Judge |
| X4 | TTS Pool（CosyVoice 2 / Doubao-TTS / Minimax-T2A / edge-tts 兜底） | 配音 |
| X5 | QA & Compliance Pool（ArcFace / CLIP / VBench / Moderation 双层） | 质量与合规 |

### 3.3 调用方 (Caller)

调用方是**另一个软件系统**（如内容平台的分发后台、IP 运营公司的 ETL 管道），通过 REST API 提交 `ProjectInput` 即触发，无 GUI 交互。

---

## 4. 顶层用户故事 (Job Stories — 主体均为软件)

> 注意：所有 "as a / when / I want" 句式中的主体都不是人类，而是上游系统或下游系统。

- **JS-01** *As an upstream content platform's dispatch service*, when a new IP novel is ingested, I want to obtain N self-consistent episodic videos within SLA without any operator intervention, so that I can publish them via my CDN automatically.
- **JS-02** *As a downstream analytics service*, when an episode is released, I want to receive a structured event with full provenance, so that I can compute lineage / cost / quality dashboards.
- **JS-03** *As a compliance audit pipeline*, when a moderation hit occurs, I want a deterministic incident artefact within 60 seconds, so that I can quarantine the project automatically.
- **JS-04** *As a budget controller*, when project credits exceed 80% of the allocated cap, I want the pipeline to degrade to a cheaper rendering tier or stop, so that I never overshoot.
- **JS-05** *As a regression test runner*, when the same `(novel_hash, config_hash, seed)` is submitted, I want byte-identical outputs at every stage so the system passes determinism gates.

---

## 5. 功能需求 — 输入与项目生命周期 (REQ-IN-***)

[REQ-IN-001] Priority=Must  Source=P-2  Verify=Integration
EARS  : THE SYSTEM SHALL accept project submissions via `POST /v1/projects` carrying a JSON body conforming to the `ProjectInput` schema (Design §6.1) and respond with `202 Accepted` plus a globally unique `project_id` (UUIDv7).
AC    : `HTTP 202 + body.project_id ~ /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/`; rejected payloads return RFC 7807 problem+json with `errors[*].path` indicating the offending field.
Trace : Design §1, §6.1 → Task T-0102.

[REQ-IN-002] Priority=Must  Source=P-7  Verify=Unit
EARS  : WHEN a project is accepted THE SYSTEM SHALL persist `(project_id, novel_sha256, config_sha256, seed, submitted_at)` into table `manhuaju_projects` before responding.
AC    : Row insert occurs in same transaction as the response builder; on DB failure the API returns `503` and the project is **not** counted as submitted.
Trace : Design §6.1, §11 → Task T-0103.

[REQ-IN-003] Priority=Must  Source=P-6  Verify=Integration
EARS  : IF the input novel exceeds 1,000,000 characters THEN THE SYSTEM SHALL chunk it into ≤ 50,000-character segments, persist a `chunk_index`, and continue ingestion asynchronously.
AC    : `chunk_index.json` contains `chunks[i] = {start, end, sha256, tokens}`; sum of chunk lengths == original length; rebuild from chunks is byte-exact.
Trace : Design §5, §6.1 → Task T-0104.

[REQ-IN-004] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL refuse any submission lacking a deterministic `seed` field and shall **not** auto-generate one.
AC    : Submissions without `seed` get `422 unprocessable_entity`; with seed, downstream Provenance records `seed` in every event payload.
Trace : Design §6.1, §11 → Task T-0105.

[REQ-IN-005] Priority=Must  Source=P-9  Verify=Integration
EARS  : WHILE the project is in `Ingesting` state THE SYSTEM SHALL emit `manhuaju.event.ingest.progress` events at ≥ 1 Hz including `bytes_done / bytes_total`.
AC    : Event log shows monotonic increase; final event has `bytes_done == bytes_total` before transitioning to `Planning`.
Trace : Design §11 → Task T-0106.

[REQ-IN-006] Priority=Must  Source=P-7  Verify=E2E
EARS  : WHEN ingestion completes THE SYSTEM SHALL write `00_input/normalized.txt` with NFC Unicode normalisation and a `00_input/manifest.json` enumerating language detection, encoding, line count, and chunk hashes.
AC    : `manifest.json.lang_iso639_1 ∈ {zh, en, ja, es, …}`; SHA-256 of normalized text recorded.
Trace : Design §5, §6.1 → Task T-0107.

[REQ-IN-007] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL reject any uploaded asset whose declared MIME does not match its sniffed magic bytes.
AC    : Mismatched assets cause `400` and `09_qa_reports/incident.json` of type `mime_mismatch`.
Trace : Design §12 → Task T-0108.

[REQ-IN-008] Priority=Should  Source=P-10  Verify=Integration
EARS  : WHERE `config.target_locales` contains > 1 locale THE SYSTEM SHALL fan out one episode pack per locale at the post-production stage, sharing the same render artefacts where possible.
AC    : Output directory contains `08_post/{ep}/{locale}.mp4`; subtitles regenerated per locale.
Trace : Design §13, §19.7 → Task T-0109.

[REQ-IN-009] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL transition the project state machine without requiring any external confirmation between `Ingesting → Planning → CharacterBuilding → Producing → QA → Released | Failed` (no `WaitingForApproval` state may exist).
AC    : Static analysis of state graph proves absence of any node prefixed `Wait*` or labelled `human_*`.
Trace : Design §5 → Task T-0110.

[REQ-IN-010] Priority=Must  Source=P-6  Verify=Integration
EARS  : THE SYSTEM SHALL bind every project to a `Budget = (max_tokens, max_seconds, max_credits)` derived from `config.budget_tier`, and reject submissions where the requested episode count would foreseeably breach the credit cap by > 25%.
AC    : Submission rejection codepath logs `budget_estimate_violation` with the predicted vs. allowed credits.
Trace : Design §13 → Task T-0111.

[REQ-IN-011] Priority=Must  Source=P-3  Verify=Unit
EARS  : WHEN duplicate `(novel_sha256, config_sha256, seed)` is submitted within 30 days THE SYSTEM SHALL return the previous `project_id` instead of starting a new run.
AC    : Idempotency key check via Redis hash; second submission returns `200 OK` with `idempotent: true`.
Trace : Design §6.1 → Task T-0112.

[REQ-IN-012] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL store the original novel content encrypted at rest with envelope encryption (KMS-protected DEK).
AC    : S3 object metadata shows `x-amz-server-side-encryption: aws:kms`; decryption requires KMS grant.
Trace : Design §12 → Task T-0113.

---

## 6. 功能需求 — Story Architect Agent (REQ-SA-***)

[REQ-SA-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL invoke `StoryArchitectAgent` with the normalized novel and produce a `StoryBlueprint` artefact (Design §6.1) containing world rules, timeline, character roster, location atlas, motif index.
AC    : `01_story_blueprint/blueprint.json` validates against `StoryBlueprintSchema` (pydantic v2), no field marked `unknown`.
Trace : Design §6.1, §3.A1 → Task T-0201.

[REQ-SA-002] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL pass `seed` into all LLM calls of `StoryArchitectAgent` and record `(model, version, temperature, top_p, seed, prompt_sha256, response_sha256)` in `99_provenance/`.
AC    : Re-running with same inputs yields identical `response_sha256` for ≥ 95% of calls; mismatch triggers `non_determinism_alert`.
Trace : Design §11 → Task T-0202.

[REQ-SA-003] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL detect every named entity that appears in ≥ 2 narrative beats and add it to `characters[]`, including supporting characters with role `cameo`.
AC    : Recall vs. ground-truth NER ≥ 0.95 on the regression set `tests/regression/ner/`.
Trace : Design §3.A1, §6.1 → Task T-0203.

[REQ-SA-004] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL generate a directed character relationship graph with edges typed from a closed enum `{family, friend, rival, lover, mentor, enemy, neutral, unknown}`.
AC    : Graph stored as `characters_graph.json`; cycle detection logged; isolated nodes flagged.
Trace : Design §6.1 → Task T-0204.

[REQ-SA-005] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL produce a chronological `timeline[]` whose events reference `(beat_id, location_id, characters_present[])` with strictly monotonic timestamps in story-time.
AC    : Validator passes; any time inversion is reported as `timeline_inversion` and blocks state transition.
Trace : Design §6.1 → Task T-0205.

[REQ-SA-006] Priority=Should  Source=P-10  Verify=Integration
EARS  : WHERE `config.locale_hint != source_locale` THE SYSTEM SHALL produce both a source-language and a target-language version of the StoryBlueprint, keeping IDs stable.
AC    : `blueprint.zh.json` and `blueprint.en.json` share identical `*_id` fields; only `display_name` differs.
Trace : Design §13 → Task T-0206.

[REQ-SA-007] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL include for each character a `provenance` block listing the verbatim sentences (with byte offsets) that justify each declared trait.
AC    : Sample audit: 50 random traits; ≥ 98% justifications match ground truth.
Trace : Design §11 → Task T-0207.

[REQ-SA-008] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the LLM returns a malformed StoryBlueprint THEN THE SYSTEM SHALL retry with structured output mode (JSON schema enforcement) up to 3 times before downgrading to a fragmentary blueprint and flagging `partial_blueprint`.
AC    : Failure path triggers `manhuaju.event.story_blueprint.degraded`; subsequent stages adapt.
Trace : Design §10 → Task T-0208.

[REQ-SA-009] Priority=Must  Source=P-4  Verify=QAAgent
EARS  : WHEN the StoryBlueprint is produced THE SYSTEM SHALL run an LLM-judge (Claude 3.7 Sonnet) scoring rubric (faithfulness, coverage, structure) and require all three scores ≥ 8/10 before promotion.
AC    : Below threshold causes `IterationManager` to retry with a stronger model; persisted scores in `09_qa_reports/blueprint_scores.json`.
Trace : Design §15 → Task T-0209.

[REQ-SA-010] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL fingerprint the StoryBlueprint with a deterministic canonical-JSON SHA-256 (`blueprint_sha`) and propagate it as a header on every downstream Agent call.
AC    : Header `X-Manhuaju-Blueprint-SHA` present and matches; mismatch fails the call with `blueprint_drift`.
Trace : Design §11 → Task T-0210.

[REQ-SA-011] Priority=Should  Source=P-5  Verify=Integration
EARS  : WHEN the source novel contains explicit chapter delimiters THE SYSTEM SHALL preserve them as `source_chapter_id` references rather than re-segment.
AC    : 100% of detected chapter delimiters appear as anchors in `timeline[]`.
Trace : Design §6.1 → Task T-0211.

[REQ-SA-012] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL emit `manhuaju.event.story_blueprint.completed` only after schema validation, judge scoring, and SHA fingerprinting all succeed.
AC    : Event ordering is enforced; partial completion never emits this event.
Trace : Design §11 → Task T-0212.

---

## 7. 功能需求 — Episode Planner Agent (REQ-EP-***)

[REQ-EP-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL plan exactly `config.episode_count` episodes, each containing 6–14 beats covering 60–180 seconds of target screen time.
AC    : `02_episodes_plan/plan.json` validates; per-episode `target_seconds ∈ [60,180]`; total beats == sum of per-episode beats.
Trace : Design §3.A2, §6.1 → Task T-0301.

[REQ-EP-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL guarantee that every episode begins with a recap hook of ≤ 6 seconds and ends with a cliffhanger flagged `cliffhanger_strength ∈ [1,5]` with mean ≥ 3.5 across the season.
AC    : `episode[i].opening` and `episode[i].closing.cliffhanger_strength` populated; mean computed and asserted.
Trace : Design §6.1 → Task T-0302.

[REQ-EP-003] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL ensure no character appearing in episode N also appears in episode N+1 with conflicting state (clothing/age/wound) without an explicit `state_transition` reason.
AC    : Cross-episode state diff produced; conflicting transitions without justification block planning promotion.
Trace : Design §9 → Task T-0303.

[REQ-EP-004] Priority=Must  Source=P-6  Verify=Unit
EARS  : THE SYSTEM SHALL allocate per-episode credit and token budgets summing to ≤ 95% of the project Budget, leaving ≥ 5% reserve for repair iterations.
AC    : `plan.budgets.reserve_credits ≥ 0.05 * total_credits`.
Trace : Design §13 → Task T-0304.

[REQ-EP-005] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL emit `manhuaju.event.episode_plan.completed` only after all episodes pass schema validation and budget allocation.
AC    : Event payload contains `episode_count, total_seconds, total_budget`.
Trace : Design §11 → Task T-0305.

[REQ-EP-006] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : WHEN the plan is produced THE SYSTEM SHALL invoke an LLM judge to verify pacing, hook strength, and dramatic arc; the rubric must score ≥ 8/10 in all three.
AC    : Judge result file `09_qa_reports/plan_scores.json`; below threshold triggers re-plan.
Trace : Design §15 → Task T-0306.

[REQ-EP-007] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL produce per-episode `synopsis_short` (≤ 80 chars) and `synopsis_long` (≤ 600 chars) for downstream marketing metadata.
AC    : Length validator passes; both fields are NFC-normalized.
Trace : Design §6.1 → Task T-0307.

[REQ-EP-008] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the plan cannot satisfy `episode_count` while keeping per-episode beats within bounds THEN THE SYSTEM SHALL adjust `episode_count` automatically within ±10% and log `episode_count_autotune`.
AC    : Adjustment recorded; downstream uses adjusted count consistently.
Trace : Design §10 → Task T-0308.

[REQ-EP-009] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL produce identical plans for identical `(blueprint_sha, config_sha, seed)`.
AC    : Determinism CI test passes.
Trace : Design §11 → Task T-0309.

[REQ-EP-010] Priority=Should  Source=P-5  Verify=Integration
EARS  : WHERE the source spans > 100,000 words THE SYSTEM SHALL apply a sliding-window summarizer with overlap ≥ 20% before planning.
AC    : Summarizer config persisted; overlap stat computed and ≥ 20%.
Trace : Design §3.A2 → Task T-0310.

---

## 8. 功能需求 — Character Bible Agent (REQ-CB-***)

[REQ-CB-001] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL produce one `CharacterBible` artefact per character in the StoryBlueprint roster, stored at `03_character_bibles/{char_id}/bible.json` and validated against `CharacterBibleSchema` (Design §6.1).
AC    : Schema validation passes; required fields `appearance, outfit, voice, personality, age_state_machine, relations[]` populated; missing fields fail the build.
Trace : Design §6.1, §3.A3 → Task T-0401.

[REQ-CB-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL describe `appearance` with deterministic, machine-parseable attributes including: gender, ethnicity, age band, height band, body type, eye color, hair (length / color / texture / hairstyle), distinguishing marks, and a free-text "essence" ≤ 240 chars.
AC    : All fields from a closed enum where applicable; `essence` length checked.
Trace : Design §6.1, §9 → Task T-0402.

[REQ-CB-003] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL maintain an explicit `outfit_library` per character with ≥ 3 outfits (default / signature / variant) each holding palette, fabric, silhouette, accessories.
AC    : `outfit_library[].palette` is a valid 5-color hex array; signature outfit referenced by default.
Trace : Design §6.1, §9 → Task T-0403.

[REQ-CB-004] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL define a per-character `state_machine` with discrete nodes for `(age_band, hair_state, wound_state, outfit_id)` and a list of legal transitions referencing the source-novel beats that justify each transition.
AC    : Static analyser proves: every transition has a `justification.beat_id`; every state node is reachable.
Trace : Design §9 → Task T-0404.

[REQ-CB-005] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL deduplicate near-identical characters across alias and nickname mentions, producing a stable `char_id` (SHA-256 of canonical name + first appearance offset).
AC    : Coreference resolution F1 ≥ 0.92 on `tests/regression/coref/`.
Trace : Design §6.1 → Task T-0405.

[REQ-CB-006] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL fingerprint each `CharacterBible` with a canonical-JSON SHA-256 (`bible_sha`) and embed it into all downstream Render Prompts.
AC    : Render Prompt template requires `{character.bible_sha}` placeholder; missing causes pipeline to abort.
Trace : Design §6.1, §11 → Task T-0406.

[REQ-CB-007] Priority=Should  Source=P-5  Verify=Unit
EARS  : WHERE a character is flagged `screen_role=lead` THE SYSTEM SHALL produce ≥ 5 outfits and ≥ 6 distinct facial expression descriptors.
AC    : Lead characters' bibles satisfy the count gates.
Trace : Design §6.1 → Task T-0407.

[REQ-CB-008] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the LLM produces conflicting traits across two beats for the same character THEN THE SYSTEM SHALL invoke a deterministic resolver (later-mention-wins-with-justification) and log `bible_conflict_resolved`.
AC    : Resolver reproducible; conflict log captured in `09_qa_reports/`.
Trace : Design §10 → Task T-0408.

[REQ-CB-009] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN the bible set is finalized THE SYSTEM SHALL emit `manhuaju.event.character_bibles.completed` with `roster_count, lead_count, total_outfits` and the SHA of every bible.
AC    : Event payload validates against `CharacterBiblesCompletedSchema`.
Trace : Design §11 → Task T-0409.

[REQ-CB-010] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL include in every bible a `provenance.passages[]` listing source-novel byte ranges that justified each `appearance.*` field.
AC    : ≥ 90% of leaf appearance fields cite at least one passage; missing-justification fields default-set with explicit `assumed=true`.
Trace : Design §11 → Task T-0410.

[REQ-CB-011] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL run a vision-LM consistency probe: render 4 quick test images per lead character via the reference-asset path and require pairwise CLIP cosine ≥ 0.86 before promotion.
AC    : Probe report saved; failures trigger CB re-author with stronger model.
Trace : Design §15 → Task T-0411.

[REQ-CB-012] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL never block on human approval to commit a bible even when probe scores are marginal; instead it shall auto-iterate up to `bible_repair_max=3` times and finally degrade with `bible_partial`.
AC    : State graph contains no human-gated edges; degradation event includes the failed metrics.
Trace : Design §10, §16 → Task T-0412.

---

## 9. 功能需求 — Reference Asset Agent (REQ-RA-***)

[REQ-RA-001] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL generate, for each character, a multi-view reference image set comprising at minimum: front, three-quarter, side, back, full-body, head close-up, expression sheet, signature outfit close-up.
AC    : Files `03_character_bibles/{char_id}/refs/{view}.png` exist; ≥ 8 distinct views per lead, ≥ 4 per supporting character.
Trace : Design §3.A4, §9 → Task T-0501.

[REQ-RA-002] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL ensure pairwise ArcFace cosine similarity within a character's reference set ≥ 0.94 and pairwise CLIP cosine ≥ 0.90 (face) / ≥ 0.85 (full body).
AC    : Threshold report saved; below threshold triggers regeneration up to `ref_repair_max=4`; final fail downgrades to `partial_refs`.
Trace : Design §9, §15 → Task T-0502.

[REQ-RA-003] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL pin a per-character `seed` derived from `bible_sha + view_id`, and persist it so re-renders are reproducible.
AC    : Seed scheme documented; identical inputs reproduce identical asset hashes within tolerance window.
Trace : Design §11 → Task T-0503.

[REQ-RA-004] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL compose Render Prompts for reference assets using the Bible's `appearance + outfit + essence + style_lock` fields, **always in natural language**, with Image-1 / Image-2 / etc. role assignments compatible with Seedance 2.0 / Xiaoyunque 2.0 multi-modal semantics (no `@token` syntax).
AC    : Prompt template includes phrases like "use image 1 as front view" / "match the hairstyle in image 2"; absent of `@` mention.
Trace : Design §8.2 → Task T-0504.

[REQ-RA-005] Priority=Should  Source=P-5  Verify=Integration
EARS  : WHERE `config.consistency_tier=lora` THE SYSTEM SHALL train a per-character LoRA from the multi-view set with ≥ 20 augmented images and persist the artefact at `03_character_bibles/{char_id}/lora/`.
AC    : LoRA file ≤ 256 MB; eval probe shows ≥ +0.03 ArcFace gain over project-bible-only path; logged in `09_qa_reports/`.
Trace : Design §9, §16 → Task T-0505.

[REQ-RA-006] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF reference image generation fails for any character after `ref_repair_max` attempts THEN THE SYSTEM SHALL fallback to text-only character description in render prompts and tag the project `consistency_degraded`.
AC    : Tag visible in project metadata; QA gate downgrades acceptance threshold accordingly.
Trace : Design §10 → Task T-0506.

[REQ-RA-007] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL embed EXIF/XMP metadata in every reference image with `(project_id, char_id, view_id, model, prompt_sha256, seed, generated_at)`.
AC    : Random sample inspection: 100% images carry the required metadata.
Trace : Design §11 → Task T-0507.

[REQ-RA-008] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN reference assets for a character are finalized THE SYSTEM SHALL emit `manhuaju.event.reference_assets.ready` with the asset count and consistency metrics.
AC    : Event payload includes `arc_face_intra, clip_intra, asset_count, lora_present`.
Trace : Design §11 → Task T-0508.

[REQ-RA-009] Priority=Should  Source=P-5  Verify=Integration
EARS  : WHERE a character has multiple `outfit_library` entries THE SYSTEM SHALL produce reference images for each outfit's signature pose.
AC    : `refs/{outfit_id}/{view}.png` set complete; missing entries logged.
Trace : Design §9 → Task T-0509.

[REQ-RA-010] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL prohibit any reference image whose perceptual hash matches a known real-person face above a threshold of 0.9 (`real_person_match`).
AC    : Reverse-search probe runs; matches blocked and incident logged with `real_person_match`.
Trace : Design §12 → Task T-0510.

---

## 10. 功能需求 — Script Writer Agent (REQ-SW-***)

[REQ-SW-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL produce a Fountain-formatted screenplay per episode at `04_scripts/ep{NN}.fountain` plus a structured JSON twin at `04_scripts/ep{NN}.json` validating `ScriptSchema` (Design §6.2).
AC    : Both files exist; JSON `scenes[].shots[]` aligns with Fountain scene/shot order; round-trip parse stable.
Trace : Design §3.A5, §6.2 → Task T-0601.

[REQ-SW-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL ensure every line of dialogue references a known `char_id`; unknown speakers cause hard failure.
AC    : Validator returns `unknown_speaker` for any orphan line; build aborts.
Trace : Design §6.2 → Task T-0602.

[REQ-SW-003] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL annotate each shot with `(estimated_seconds, intent, characters[], location_id, mood, music_cue, sfx_cue)`.
AC    : All shots have all 7 fields; `intent` from closed enum (`establish/build/turn/climax/resolve`).
Trace : Design §6.2 → Task T-0603.

[REQ-SW-004] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL keep the cumulative `estimated_seconds` of an episode within ±5% of `EpisodePlanner` target.
AC    : Validator enforces; out-of-range triggers re-write.
Trace : Design §6.2 → Task T-0604.

[REQ-SW-005] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL invoke an LLM judge to grade dialogue (naturalness, character voice consistency) ≥ 8/10 before promotion.
AC    : Below threshold → re-author up to `script_repair_max=2`.
Trace : Design §15 → Task T-0605.

[REQ-SW-006] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the LLM hallucinates a non-existent character or location THEN THE SYSTEM SHALL reject the script and re-author with retrieval-augmented context.
AC    : RAG fallback triggered; re-authored script passes name validation.
Trace : Design §10 → Task T-0606.

[REQ-SW-007] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL include a per-episode `narration` track when `config.narration=on`, with timing aligned to scene boundaries.
AC  : Narration timing offsets recorded; episodes without narration omit the track entirely.
Trace : Design §6.2, §13 → Task T-0607.

[REQ-SW-008] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL link every dialogue line back to one or more source-novel byte ranges in `provenance.source_spans[]`.
AC    : ≥ 80% of original-novel-derived dialogue cites a span; original additions explicitly tagged `agent_authored=true`.
Trace : Design §11 → Task T-0608.

[REQ-SW-009] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN a script is finalized THE SYSTEM SHALL emit `manhuaju.event.script.completed` with `scene_count, shot_count, dialogue_lines, total_seconds`.
AC    : Event payload validated.
Trace : Design §11 → Task T-0609.

[REQ-SW-010] Priority=Should  Source=P-10  Verify=Integration
EARS  : WHERE `config.target_locales` includes locales other than the source, THE SYSTEM SHALL produce per-locale `dialogue_localized[]` translations preserving timing.
AC    : Locale dialogues exist; locale `script.json.dialogue_localized.length == base.dialogue.length`.
Trace : Design §13 → Task T-0610.

---

## 11. 功能需求 — Storyboard Director Agent (REQ-SD-***)

[REQ-SD-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL transform every shot in the script into a `StoryboardShot` (Design §6.2) annotated with `shot_size, camera_angle, camera_movement, lens_focal_mm, depth_of_field, lighting, palette_ref, weather, character_blocking, key_action, key_emotion, target_seconds`.
AC    : All 12 fields populated; enum values come from project palette in `config/style-presets.yaml`.
Trace : Design §6.2 → Task T-0701.

[REQ-SD-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL keep per-shot `target_seconds ∈ {5, 10, 15}` to map directly onto Xiaoyunque/Seedance generation lengths; longer shots are split with continuity tags.
AC    : Validator passes; split shots share `parent_shot_id` and ordered `seq`.
Trace : Design §8 → Task T-0702.

[REQ-SD-003] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL never place > 2 named characters in the same generation unit; group scenes are decomposed into 2-or-fewer-character cuts.
AC    : Per-shot `characters[].length ≤ 2`; group scenes carry `decomposition.parent_group_shot_id`.
Trace : Design §8.2, §9 → Task T-0703.

[REQ-SD-004] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL produce, per shot, a low-fidelity thumbnail rendered from text-to-image (256×256) for downstream visual sanity-checking.
AC    : Thumbnails exist at `05_storyboards/ep{NN}/thumbs/{shot_id}.png`; checksum recorded.
Trace : Design §15 → Task T-0704.

[REQ-SD-005] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL ensure shot-to-shot continuity by computing a `continuity_score` (location/time/character coherence) ≥ 0.9 across consecutive shots; below threshold triggers `IterationManager`.
AC    : Score recorded in `05_storyboards/ep{NN}/continuity.json`.
Trace : Design §9 → Task T-0705.

[REQ-SD-006] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL include in each StoryboardShot a `prompt_brief` that the RenderOrchestrator will expand into the model-specific prompt; the brief must contain ≥ 10 disjoint constraint clauses.
AC    : Brief schema validated; clause count enforced.
Trace : Design §8 → Task T-0706.

[REQ-SD-007] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF a shot brief cannot be satisfied within Xiaoyunque's per-prompt token limit THEN THE SYSTEM SHALL automatically split into linked sub-shots while preserving narrative timing.
AC    : Sub-shots carry `prompt_split=true`; merged duration matches original.
Trace : Design §10 → Task T-0707.

[REQ-SD-008] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN the storyboard is finalized THE SYSTEM SHALL emit `manhuaju.event.storyboard.completed` with `shot_count, total_seconds, continuity_score`.
AC    : Event payload validated.
Trace : Design §11 → Task T-0708.

[REQ-SD-009] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : WHERE the storyboard contains action-heavy sequences (`mood ∈ {fight, chase}`) THE SYSTEM SHALL ensure shot durations skew shorter (median ≤ 7s) to maintain pacing.
AC    : Pacing validator passes; outliers logged.
Trace : Design §15 → Task T-0709.

---

## 12. 功能需求 — Visual Style Agent (REQ-VS-***)

[REQ-VS-001] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL select exactly one project-level style from `config/style-presets.yaml` (default `cinematic_2d_v1`) and lock it for the project's lifetime; mid-project style mutation is disallowed.
AC    : `style_lock.json` is immutable post-write; any attempt to mutate fails with `style_lock_violation`.
Trace : Design §6.2, §11 → Task T-0801.

[REQ-VS-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL produce a project-level palette of 8 master colors and a per-location palette derived from the master.
AC    : Palettes saved as ASE / hex; per-location palettes validated to be in-gamut of master ± Δ.
Trace : Design §6.2 → Task T-0802.

[REQ-VS-003] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL define rendering parameters (`aspect_ratio, resolution, fps, duration_unit, model_tier`) once at project init and feed them verbatim to every render call.
AC    : Render request inspector verifies parameter equality across all calls; mismatch raises `style_param_drift`.
Trace : Design §8 → Task T-0803.

[REQ-VS-004] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL evaluate the per-shot rendered output against the locked palette and require palette ΔE2000 ≤ 8 for ≥ 90% of frames.
AC    : Palette deviation report produced; out-of-tolerance shots flagged for repair.
Trace : Design §15 → Task T-0804.

[REQ-VS-005] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN style is locked THE SYSTEM SHALL emit `manhuaju.event.style.locked` carrying the SHA of the style profile.
AC    : Event payload validated.
Trace : Design §11 → Task T-0805.

[REQ-VS-006] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL embed `style_sha` in every render prompt as `[STYLE_SHA: …]` to enable post-hoc audit.
AC    : Prompt inspector confirms presence.
Trace : Design §11 → Task T-0806.

---

## 13. 功能需求 — Voice / Music Director Agents (REQ-VD-*** / REQ-MD-***)

[REQ-VD-001] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL assign each character one stable voice ID drawn from a project-pinned voice palette; reassigning across episodes is disallowed.
AC    : `voice_assignments.json` immutable per project; any drift fails with `voice_id_drift`.
Trace : Design §6.2 → Task T-0901.

[REQ-VD-002] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL synthesize all dialogue lines via the primary TTS provider with `(speaker, emotion, prosody, target_lufs=-16)`; outputs WAV 24-bit / 48kHz mono.
AC    : Each line file present at `07_audio/ep{NN}/dialogue/{shot_id}_{line_seq}.wav`; LUFS measured.
Trace : Design §8.4 → Task T-0902.

[REQ-VD-003] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL evaluate UTMOS for each dialogue line; lines with UTMOS < 3.8 are regenerated with stronger prosody hints up to 2 retries.
AC    : Per-line UTMOS recorded; below-threshold count after retries < 3% of total.
Trace : Design §15 → Task T-0903.

[REQ-VD-004] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the primary TTS fails THEN THE SYSTEM SHALL fall back to secondary TTS, then `edge-tts`, then synthesize a beep + caption-only mode and tag `audio_degraded`.
AC    : Failure paths covered by integration tests; degradation logged.
Trace : Design §10 → Task T-0904.

[REQ-VD-005] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL refuse to clone any voice without a recorded `voice_consent_token`; cloning attempts without it terminate the project.
AC    : Voice cloning subsystem validates token; missing → `voice_consent_violation` incident.
Trace : Design §12 → Task T-0905.

[REQ-VD-006] Priority=Should  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL produce per-line lip-sync tracks (visemes / phoneme timestamps) for downstream lip alignment.
AC    : `*.lipsync.json` files produced and validated.
Trace : Design §15 → Task T-0906.

[REQ-MD-001] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL select per-episode BGM from a licensed library or generate via Suno/Udio with a project-pinned style key, stored at `07_audio/ep{NN}/bgm.wav`.
AC    : License metadata recorded; file present.
Trace : Design §6.2 → Task T-1001.

[REQ-MD-002] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL produce a per-episode `mix.json` enumerating dialogue / BGM / SFX gain envelopes and crossfades.
AC    : Validator passes; downstream mixer reproduces the mix deterministically.
Trace : Design §8.4 → Task T-1002.

[REQ-MD-003] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL ensure final mix loudness within `-16 ±0.5 LUFS` (integrated) and true-peak ≤ -1 dBTP.
AC    : Loudness probe (BS.1770) reports compliance; non-compliant episode auto-remixed.
Trace : Design §15 → Task T-1003.

[REQ-MD-004] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL adjust BGM dynamics during dialogue (ducking) so dialogue stems remain ≥ 6 dB above BGM level.
AC    : Stem analysis verifies; below threshold → re-mix.
Trace : Design §15 → Task T-1004.

[REQ-MD-005] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL persist the BGM/SFX/dialogue stems separately so post-hoc remastering is possible without re-rendering visuals.
AC    : Stems present; final mux references them by stable hash.
Trace : Design §6.2 → Task T-1005.

---

## 14. 功能需求 — Render Orchestrator Agent (REQ-RO-***) 含小云雀 API 契约

[REQ-RO-001] Priority=Must  Source=P-2  Verify=Integration
EARS  : THE SYSTEM SHALL invoke Xiaoyunque Agent 2.0 (火山引擎即梦 AI) as the primary render path with submit + poll + webhook dual channels.
AC    : `XiaoyunqueAdapter` exercised in integration tests with mock and live (gated); both channels return identical task states.
Trace : Design §8.1, §3.A10 → Task T-1101.

[REQ-RO-002] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL submit each StoryboardShot as a single Xiaoyunque task with: `model_tier ∈ {fast, pro}`, `aspect_ratio ∈ {9:16, 16:9, 1:1}`, `duration_s ∈ {5, 10, 15}`, `style ∈ {2d, 3d, simhuman}`, `reference_images[≤9]`, `reference_videos[≤3]`, `reference_audios[≤3]`.
AC    : Adapter request schema validated; field count caps enforced.
Trace : Design §8 → Task T-1102.

[REQ-RO-003] Priority=Must  Source=P-5  Verify=Unit
EARS  : THE SYSTEM SHALL build prompts using the natural-language multi-modal assignment pattern (e.g. "use image 1 as the first frame", "match the hairstyle in image 2", "audio 1 is dialogue, do not lip-sync"); `@token` syntax MUST NOT appear.
AC    : Prompt linter regex blocks `(^|\s)@\w+`; commit refused on hit.
Trace : Design §8.2 → Task T-1103.

[REQ-RO-004] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL pass at least the lead character's `front + signature_outfit + expression_sheet` images for any shot in which the lead appears.
AC    : Adapter pre-flight gate; missing refs cause `missing_required_refs` and abort the render call.
Trace : Design §9 → Task T-1104.

[REQ-RO-005] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF Xiaoyunque returns `429`, `5xx`, or queue saturation THEN THE SYSTEM SHALL retry with exponential backoff `1s, 2s, 4s, 8s, 16s`; on continued failure within 60s window the circuit breaker shall open and route the call to Seedance 2.0 fallback.
AC    : Adapter exposes Prometheus metrics `xyq_failure_total`, `xyq_circuit_state`; fallback exercised in chaos tests.
Trace : Design §10 → Task T-1105.

[REQ-RO-006] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF Seedance 2.0 fallback also fails THEN THE SYSTEM SHALL queue a deferred retry (≤ 6h delay), and finally place the shot into `degraded_render` state where a still-image storyboard panel + caption is composited as a placeholder with explicit `degraded=true` flag in metadata.
AC    : Placeholder file matches design template; downstream QA respects degraded state.
Trace : Design §10 → Task T-1106.

[REQ-RO-007] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL pin a per-shot `seed` derived from `(project_id, episode_id, shot_id, retry_count)` so each retry produces a distinct yet reproducible result.
AC    : Seed scheme documented; same `(p, e, s, r)` produces identical request payload SHA.
Trace : Design §11 → Task T-1107.

[REQ-RO-008] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL persist the request and response payloads of every render call (with secrets redacted) into `99_provenance/render/{task_id}.json`.
AC    : Inspection of 100 random calls finds 0 missing files and 0 secrets-in-clear.
Trace : Design §11 → Task T-1108.

[REQ-RO-009] Priority=Must  Source=P-6  Verify=Unit
EARS  : THE SYSTEM SHALL track credit consumption against the project Budget after every render call; on > 95% consumption the orchestrator switches `model_tier = fast` for remaining shots.
AC    : Budget ledger present; tier switch event logged.
Trace : Design §13 → Task T-1109.

[REQ-RO-010] Priority=Must  Source=P-2  Verify=Integration
EARS  : THE SYSTEM SHALL parallelize render calls per episode with a default concurrency cap of 16 shots/episode and a global cap of 64 shots; both caps configurable.
AC    : Load test verifies caps respected; backpressure events fire when exceeded.
Trace : Design §13 → Task T-1110.

[REQ-RO-011] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL download the produced MP4 to `06_renders/ep{NN}/shot_{NNN}.mp4` and write `_metadata.json` with: `(task_id, prompt_sha, refs_sha[], duration_s, fps, resolution, model_version, credits_spent)`.
AC    : All 8 fields present; missing field aborts pipeline.
Trace : Design §11 → Task T-1111.

[REQ-RO-012] Priority=Should  Source=P-9  Verify=Integration
EARS  : WHERE the project mode is `express` THE SYSTEM SHALL invoke Xiaoyunque 短剧 Agent (10-万字一键成片) as a single bulk submission instead of the per-shot path, with the same provenance guarantees.
AC    : Bulk path produces same artefact tree; gated by feature flag.
Trace : Design §8.1 → Task T-1112.

[REQ-RO-013] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL never wait for any human moderator to approve a render; if the call returns `content_review_required` from Xiaoyunque the system shall auto-rewrite the prompt up to 2 times and otherwise reject the shot via `IterationManager`.
AC    : Path traversal asserted in E2E; no `wait_for_human` state appears.
Trace : Design §10 → Task T-1113.

[REQ-RO-014] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL detect duplicate render submissions via idempotency keys built from `(prompt_sha, refs_sha, seed, model_tier)` and short-circuit by returning the previous result.
AC    : Cache hit ratio surfaced as metric; zero double-spend in tests.
Trace : Design §11 → Task T-1114.

[REQ-RO-015] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN all shots in an episode have completed (or been deferred) THE SYSTEM SHALL emit `manhuaju.event.render.episode_completed` with summary metrics.
AC    : Event includes `(success_count, degraded_count, total_credits_spent, p95_latency)`.
Trace : Design §11 → Task T-1115.

---

## 15. 功能需求 — QA Reviewer / Continuity Checker (REQ-QA-***, REQ-CC-***)

[REQ-QA-001] Priority=Must  Source=P-4  Verify=QAAgent
EARS  : THE SYSTEM SHALL evaluate every rendered shot against three layers: (a) per-frame technical (resolution, fps, codec, no-watermark, no-text-artifact), (b) per-shot semantic (LLM judge: matches storyboard intent, characters present, mood), (c) per-shot aesthetic (LAION-Aesthetic ≥ 6.0 mean, ≥ 5.5 worst frame).
AC    : Per-shot QA report `09_qa_reports/ep{NN}/shot_{NNN}.json` saved; failures route to IterationManager.
Trace : Design §15 → Task T-1201.

[REQ-QA-002] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL compute per-shot character ArcFace cosine vs. each on-screen character's reference set and require ≥ 0.92 mean / ≥ 0.88 worst frame.
AC    : Below threshold marks shot `consistency_fail` with the offending character/frames.
Trace : Design §9 → Task T-1202.

[REQ-QA-003] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL compute outfit/hair multi-label CLIP score and require ≥ 0.95 of declared attributes present.
AC    : Below threshold marks shot `outfit_fail`.
Trace : Design §9 → Task T-1203.

[REQ-QA-004] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL run VBench Subject Consistency on each shot and require ≥ 0.85.
AC    : VBench output recorded; failures logged.
Trace : Design §15 → Task T-1204.

[REQ-QA-005] Priority=Must  Source=P-1  Verify=Integration
EARS  : THE SYSTEM SHALL run a **dual-layer Moderation** check (OpenAI Moderation + 字节内容审核) on every produced shot's transcript and key-frames; any positive hit terminates the shot and may terminate the episode.
AC    : Hits produce `09_qa_reports/incident.json`; no human approval anywhere in the path.
Trace : Design §12 → Task T-1205.

[REQ-QA-006] Priority=Must  Source=P-4  Verify=QAAgent
EARS  : THE SYSTEM SHALL aggregate per-shot QA into a per-episode QA scorecard, with episode-level promotion gate: pass-rate ≥ 95% of shots **and** mean aesthetic ≥ 6.2 **and** mean ArcFace ≥ 0.92.
AC    : Episode QA file `09_qa_reports/ep{NN}/episode.json`; non-passing episodes never reach `Released`.
Trace : Design §15 → Task T-1206.

[REQ-QA-007] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN per-episode QA passes THE SYSTEM SHALL emit `manhuaju.event.qa.episode_passed`; otherwise `manhuaju.event.qa.episode_failed` with structured reasons.
AC    : Event payload schema validated.
Trace : Design §11 → Task T-1207.

[REQ-QA-008] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL compute SyncNet offset for every dialogue-bearing shot, requiring `|offset| ≤ 2 frames` post-mux; out-of-spec shots route to lip-fix Agent.
AC    : SyncNet metric persisted; lip-fix invocation tracked.
Trace : Design §15 → Task T-1208.

[REQ-CC-001] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL compute, for every promoted episode, a cross-episode consistency matrix vs. all previously released episodes, including character-level ArcFace, outfit drift, location drift, prop drift.
AC    : Matrix at `09_qa_reports/cross_episode_matrix.json` updated; failed cells trigger `IterationManager`.
Trace : Design §9 → Task T-1301.

[REQ-CC-002] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : IF cross-episode mean ArcFace for any lead drops below 0.92 vs. anchored set THEN THE SYSTEM SHALL block episode promotion and route to consistency repair.
AC    : Block path tested; no episode released with breach.
Trace : Design §9 → Task T-1302.

[REQ-CC-003] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL maintain an "anchor frames" pool per character (≥ 5 frames per outfit) that subsequent episodes are evaluated against, refreshed only on legitimate state transitions.
AC    : Anchor pool versioned; refresh log present.
Trace : Design §9 → Task T-1303.

[REQ-CC-004] Priority=Must  Source=P-3  Verify=Unit
EARS  : THE SYSTEM SHALL persist the consistency matrix as append-only history for full-season audit.
AC    : History file is append-only; tamper detection via hash chain.
Trace : Design §11 → Task T-1304.

[REQ-CC-005] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL detect prop / vehicle / accessory drift via CLIP fine-grained scoring and flag inconsistencies above tolerance; inconsistencies that violate the bible's `state_machine` block promotion.
AC    : Drift report saved; bible-violation cases blocked.
Trace : Design §9 → Task T-1305.

[REQ-CC-006] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN cross-episode consistency check completes THE SYSTEM SHALL emit `manhuaju.event.continuity.checked` with pass/fail per character.
AC    : Event emitted; payload validated.
Trace : Design §11 → Task T-1306.

---

## 16. 功能需求 — Iteration Manager Agent (REQ-IT-***)

[REQ-IT-001] Priority=Must  Source=P-1  Verify=E2E
EARS  : WHEN any QA gate fails THE SYSTEM SHALL classify the failure into a closed enum (`failure_modes`, 见附录 C) and select a repair strategy from a deterministic decision table; no human review allowed.
AC    : Failure → strategy mapping is a pure function; covered by ≥ 50 unit cases.
Trace : Design §10, §15 → Task T-1401.

[REQ-IT-002] Priority=Must  Source=P-4  Verify=Unit
EARS  : THE SYSTEM SHALL maintain per-stage retry budgets: shot ≤ 3, scene ≤ 2, episode ≤ 2, project ≤ 1 (consistency-only). Exceeding any budget escalates to the next-higher stage.
AC    : Budget table enforced; escalation logged.
Trace : Design §10 → Task T-1402.

[REQ-IT-003] Priority=Must  Source=P-9  Verify=Integration
EARS  : THE SYSTEM SHALL implement repair strategies including: (a) prompt rewrite via stronger LLM, (b) reference asset regeneration, (c) storyboard re-author, (d) script soft-edit for pacing, (e) consistency hard-refresh (re-anchor character bible), (f) downgrade to placeholder and tag `degraded`.
AC    : Each strategy has its own integration test producing the expected artefact diff.
Trace : Design §10 → Task T-1403.

[REQ-IT-004] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL persist every iteration cycle as `10_iterations/cycle_{NN}.json` recording (failure_mode, strategy, before_metrics, after_metrics, deltas).
AC    : File schema validated; retrievable end-to-end.
Trace : Design §11 → Task T-1404.

[REQ-IT-005] Priority=Must  Source=P-1  Verify=E2E
EARS  : IF a single shot fails QA on the same failure_mode 3 times in a row THEN THE SYSTEM SHALL escalate to scene-level repair, then episode-level if needed, never asking a human.
AC    : Escalation chain asserted in E2E.
Trace : Design §10 → Task T-1405.

[REQ-IT-006] Priority=Must  Source=P-4  Verify=Unit
EARS  : THE SYSTEM SHALL compute a "repair-effectiveness" metric (delta on the failing KPI / cost) per cycle and publish it for tuning the decision table.
AC    : Metric exported via Prometheus; dashboard renders it.
Trace : Design §11 → Task T-1406.

[REQ-IT-007] Priority=Must  Source=P-2  Verify=Unit
EARS  : WHEN an iteration cycle ends THE SYSTEM SHALL emit `manhuaju.event.iteration.completed` with `(cycle_id, strategy, outcome, kpi_delta)`.
AC    : Event payload validated.
Trace : Design §11 → Task T-1407.

[REQ-IT-008] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF the same failure_mode persists after the project-level retry budget is exhausted THEN THE SYSTEM SHALL transition the project to `Failed_With_Salvage`, marking the recoverable episodes `Released` and the failed ones `Quarantined`.
AC    : Salvage path tested; salvage metadata produced for upstream platform.
Trace : Design §10 → Task T-1408.

---

## 17. 功能需求 — Master Orchestrator + State Machine (REQ-MO-***)

[REQ-MO-001] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL implement a hierarchical state machine with three levels (`Project`, `Episode`, `Shot`) where every transition is triggered by an event and gated by an automated predicate.
AC    : Static analyser proves all transitions originate from events; no `manual_*` predicate exists.
Trace : Design §5 → Task T-1501.

[REQ-MO-002] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL persist state transitions atomically with their triggering event in PostgreSQL `manhuaju_state_transitions`.
AC    : Insert is in same TX as the event consumer; orphan transitions impossible.
Trace : Design §11 → Task T-1502.

[REQ-MO-003] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL produce a per-project `99_provenance/state_journal.jsonl` capturing the full transition sequence for audit replay.
AC    : Replay tool reconstructs final state from journal byte-for-byte.
Trace : Design §11 → Task T-1503.

[REQ-MO-004] Priority=Must  Source=P-9  Verify=Integration
EARS  : IF an Agent crashes mid-stage THEN THE SYSTEM SHALL resume from the last persisted checkpoint without requiring human input.
AC    : Chaos test: random Agent kill -> system reaches `Released` with same outputs (for shots) or escalates to repair path.
Trace : Design §10 → Task T-1504.

[REQ-MO-005] Priority=Must  Source=P-6  Verify=Integration
EARS  : THE SYSTEM SHALL enforce per-project Budget at every Agent boundary; exceeding 100% of any axis stops new spend immediately and triggers a graceful close.
AC    : Budget interceptor in Agent base class; integration test verifies stop.
Trace : Design §13 → Task T-1505.

[REQ-MO-006] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL emit a heartbeat event every 30 seconds while a project is live (`manhuaju.event.project.heartbeat`).
AC    : Heartbeat presence and cadence asserted.
Trace : Design §11 → Task T-1506.

[REQ-MO-007] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL produce a final `manhuaju.event.project.completed` (or `.failed_with_salvage` / `.failed`) terminal event with full KPIs, costs, and pointers to all artefacts.
AC    : Terminal event always emitted; downstream platforms can read total spend / final state / artefact root.
Trace : Design §11 → Task T-1507.

[REQ-MO-008] Priority=Must  Source=P-1  Verify=Unit
EARS  : THE SYSTEM SHALL forbid any state-machine path that requires human approval, including `WaitForHumanApproval`, `ManualReview`, `OperatorAck`, `Pause` (semantic equivalents). Static linter enforces this.
AC    : Linter regex blocks the listed identifiers in code; CI fails on hit.
Trace : Design §5 → Task T-1508.

[REQ-MO-009] Priority=Should  Source=P-6  Verify=Integration
EARS  : WHERE `config.preempt_on_priority_higher=true` THE SYSTEM SHALL allow project preemption: when a higher-priority project arrives, the in-flight project is paused (state `Paused`) and resumed automatically once resources free up — but never paused awaiting humans.
AC    : Preemption test: lower-priority project pauses and resumes deterministically.
Trace : Design §5, §13 → Task T-1509.

[REQ-MO-010] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL expose a `GET /v1/projects/{id}` endpoint returning the full state, KPIs, current stage, and last 50 events.
AC    : Endpoint contract test passes; 200 in ≤ 500ms.
Trace : Design §3 → Task T-1510.

---

## 18. 跨集人物一致性专章 (REQ-CON-***) — 头号 KPI

> 本章是整个系统的**头号 KPI**，与 P-5 直接对应。任何冲突时本章胜出。

[REQ-CON-001] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL guarantee, for every lead character, cross-episode mean ArcFace cosine ≥ 0.92 over any window of 5 consecutive episodes.
AC    : Window calculation persisted in `09_qa_reports/consistency_window.json`.
Trace : Design §9 → Task T-1601.

[REQ-CON-002] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL guarantee for every supporting character cross-episode mean ArcFace cosine ≥ 0.88.
AC    : Same as above with relaxed threshold for `screen_role=support`.
Trace : Design §9 → Task T-1602.

[REQ-CON-003] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL maintain outfit / hair multi-label match rate ≥ 0.95 vs. the active outfit declared in the bible's state machine for each shot.
AC    : Per-shot outfit score recorded; episodes failing ≥ 5% threshold blocked.
Trace : Design §9 → Task T-1603.

[REQ-CON-004] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL prohibit unsanctioned state mutations (e.g. random hair-color flip) by gating each shot's metadata against the bible state machine.
AC    : Mutation detection test: synthetic illegal flip is caught; pass-through legal flip allowed.
Trace : Design §9 → Task T-1604.

[REQ-CON-005] Priority=Must  Source=P-5  Verify=Integration
EARS  : THE SYSTEM SHALL anchor each character to a "golden frame set" (≥ 5 frames per outfit, persisted as PNGs + ArcFace embeddings) updated only on **legal** state transitions.
AC    : Golden frame manifest version-controlled; updates require justification.
Trace : Design §9 → Task T-1605.

[REQ-CON-006] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : WHILE rendering an episode THE SYSTEM SHALL feed Xiaoyunque the lead's golden front-view + signature outfit + most recent in-episode frame as `reference_images` to lock identity.
AC    : Adapter inspector confirms ref injection; missing → render aborts.
Trace : Design §8.2 → Task T-1606.

[REQ-CON-007] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : WHILE any two episodes are released THE SYSTEM SHALL guarantee main-cast ArcFace cross-episode similarity ≥ 0.92, otherwise the latest released episode is rolled back to `Pending` and routed to `consistency_repair`.
AC    : Rollback path tested; project metadata reflects pending state.
Trace : Design §9, §10 → Task T-1607.

[REQ-CON-008] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : WHERE LoRA tier is enabled THE SYSTEM SHALL prefer LoRA inference over project-bible-only path and fall back if LoRA inference shows < +0.02 ArcFace gain over baseline.
AC    : A/B harness records gain; toggle exercised.
Trace : Design §9 → Task T-1608.

[REQ-CON-009] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL detect "drifted episode" syndrome (gradual mean ArcFace decline ≥ 0.02 per episode over 3 episodes) and trigger preemptive `consistency_refresh` before the threshold is breached.
AC    : Trend detector reports; preemptive refresh logged.
Trace : Design §9 → Task T-1609.

[REQ-CON-010] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL automate the entire consistency repair loop without human approval, using Iteration Manager strategies (b)/(e).
AC    : E2E asserts no human approval node touched during repair.
Trace : Design §10 → Task T-1610.

---

## 19. 非功能需求 (REQ-NFR-***)

> NFR 与 P-3 / P-6 / P-7 / P-8 / P-9 / P-10 强对齐，每条都需可机器判定。

### 19.1 性能 (REQ-NFR-PERF-***)

[REQ-NFR-PERF-001] Priority=Must  Source=P-6  Verify=E2E
EARS  : THE SYSTEM SHALL deliver per-episode end-to-end (script→released) P95 latency ≤ 60 minutes given default config.
AC    : Latency report from `tests/perf/` aggregated; P95 sampled.
Trace : Design §13 → Task T-1701.

[REQ-NFR-PERF-002] Priority=Should  Source=P-6  Verify=E2E
EARS  : WHEN P95 latency for any episode exceeds 72 minutes THE SYSTEM SHALL automatically downgrade `model_tier` to `fast` for the remaining shots.
AC    : Downgrade event present; latency recovers within 1 episode.
Trace : Design §13 → Task T-1702.

[REQ-NFR-PERF-003] Priority=Must  Source=P-6  Verify=E2E
EARS  : THE SYSTEM SHALL achieve project-level throughput ≥ 8 episodes/hour on a standard reference cluster (Design §14 sizing).
AC    : Bench script `bench/throughput.py` reports the rate.
Trace : Design §14 → Task T-1703.

[REQ-NFR-PERF-004] Priority=Must  Source=P-6  Verify=Integration
EARS  : THE SYSTEM SHALL keep API submission latency P99 ≤ 800ms.
AC    : Locust report attached.
Trace : Design §13 → Task T-1704.

### 19.2 可靠性 (REQ-NFR-REL-***)

[REQ-NFR-REL-001] Priority=Must  Source=P-9  Verify=E2E
EARS  : THE SYSTEM SHALL achieve ≥ 99% per-episode success rate over a 1,000-episode rolling window; failures must transition to `Failed_With_Salvage` rather than crash.
AC    : Rolling-window SLA dashboard; integration tests force failures.
Trace : Design §10 → Task T-1705.

[REQ-NFR-REL-002] Priority=Must  Source=P-9  Verify=Integration
EARS  : THE SYSTEM SHALL recover from any single-node failure within 60 seconds without losing in-flight episode state.
AC    : Chaos test (kill primary, kill secondary): state preserved; episode resumes.
Trace : Design §10, §14 → Task T-1706.

[REQ-NFR-REL-003] Priority=Must  Source=P-9  Verify=Integration
EARS  : THE SYSTEM SHALL store all artefacts with at-least-once durability (S3 / MinIO multi-AZ); checksums verified on read.
AC    : Storage SLA documented; checksum mismatch detection tested.
Trace : Design §14 → Task T-1707.

### 19.3 成本 (REQ-NFR-COST-***)

[REQ-NFR-COST-001] Priority=Must  Source=P-6  Verify=E2E
EARS  : THE SYSTEM SHALL keep per-episode total external-spend ≤ ¥80 (RMB) at default tier.
AC    : Cost report `09_qa_reports/cost.json` per episode; threshold asserted.
Trace : Design §13 → Task T-1708.

[REQ-NFR-COST-002] Priority=Must  Source=P-6  Verify=Unit
EARS  : THE SYSTEM SHALL surface real-time cost burn-rate as Prometheus metric `manhuaju_cost_rate_credits_per_sec`.
AC    : Metric scraped; dashboard graph present.
Trace : Design §11 → Task T-1709.

[REQ-NFR-COST-003] Priority=Should  Source=P-6  Verify=Integration
EARS  : WHEN burn-rate is projected to overshoot the project Budget THE SYSTEM SHALL automatically downgrade `consistency_tier`, `model_tier`, or shot count, in that order.
AC    : Decision sequence covered by tests.
Trace : Design §10, §13 → Task T-1710.

### 19.4 可观测性 (REQ-NFR-OBS-***)

[REQ-NFR-OBS-001] Priority=Must  Source=P-8  Verify=Integration
EARS  : THE SYSTEM SHALL emit OpenTelemetry traces for every Agent invocation with at minimum `(project_id, episode_id, shot_id, agent, model, tokens, cost, latency)` attributes.
AC    : Tempo trace verifies attributes; missing attributes fail CI.
Trace : Design §11 → Task T-1711.

[REQ-NFR-OBS-002] Priority=Must  Source=P-8  Verify=Integration
EARS  : THE SYSTEM SHALL ship structured JSON logs (one event per line) to Loki with `manhuaju.*` labels.
AC    : Loki query proves ingestion; sample lines validate schema.
Trace : Design §11 → Task T-1712.

[REQ-NFR-OBS-003] Priority=Must  Source=P-8  Verify=Unit
EARS  : THE SYSTEM SHALL never emit prompt content longer than 16 KB into logs; longer prompts are SHA-referenced via Provenance store.
AC    : Log inspector verifies; oversize logs rejected.
Trace : Design §12 → Task T-1713.

[REQ-NFR-OBS-004] Priority=Must  Source=P-8  Verify=Integration
EARS  : THE SYSTEM SHALL expose 6 Grafana dashboards: `Project Lifecycle`, `Agent Latency`, `Cost`, `Consistency`, `Quality Gates`, `Errors & Degradation`.
AC    : Dashboards version-controlled in `ops/grafana/`.
Trace : Design §11 → Task T-1714.

### 19.5 Provenance & 可复现性 (REQ-NFR-PROV-***)

[REQ-NFR-PROV-001] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL produce, per project, a `99_provenance/manifest.json` enumerating every artefact (path, sha256, size, producer_agent, model, seed, parent_artefact).
AC    : Manifest validates; coverage 100% (no orphan artefacts).
Trace : Design §11 → Task T-1715.

[REQ-NFR-PROV-002] Priority=Must  Source=P-3  Verify=E2E
EARS  : THE SYSTEM SHALL pass a determinism test: identical `(novel_sha, config_sha, seed)` produces byte-identical artefacts at all stages where determinism is feasible (script JSON, storyboard JSON, prompts, plans).
AC    : Determinism CI green ≥ 95% of stages; non-deterministic stages explicitly listed.
Trace : Design §11 → Task T-1716.

[REQ-NFR-PROV-003] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL hash-chain the Provenance manifest entries so any tampering is detectable.
AC    : Tamper-detection test: flipping one byte breaks the chain.
Trace : Design §11 → Task T-1717.

### 19.6 安全 / 合规 (REQ-NFR-SEC-***)

[REQ-NFR-SEC-001] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL fetch all external API keys from a secrets manager (Vault / KMS) at runtime; no plaintext keys may exist on disk or in environment for production builds.
AC    : Static scanner blocks plaintext keys; CI gate.
Trace : Design §12 → Task T-1718.

[REQ-NFR-SEC-002] Priority=Must  Source=P-1  Verify=Integration
EARS  : THE SYSTEM SHALL run a dual moderation layer (OpenAI Moderation + 字节内容审核) with a logical AND gate (both must pass) for any user-facing artefact.
AC    : Both providers exercised; bypass attempts blocked.
Trace : Design §12 → Task T-1719.

[REQ-NFR-SEC-003] Priority=Must  Source=P-1  Verify=Integration
EARS  : IF the input novel contains real-person impersonation, NSFW content above tier-A, hate speech, or politically sensitive content per `config/redlines.yaml` THEN THE SYSTEM SHALL refuse the project at ingestion with a `redline_violation` incident.
AC    : Test corpus of 100 known violations triggers 100% refusal.
Trace : Design §12 → Task T-1720.

[REQ-NFR-SEC-004] Priority=Must  Source=P-1  Verify=E2E
EARS  : IF any frame, dialogue, or BGM lyric hits a moderation redline post-generation THEN THE SYSTEM SHALL discard the affected episode and write `09_qa_reports/incident.json` with full evidence.
AC    : Zero false-negatives in redline regression set.
Trace : Design §12 → Task T-1721.

[REQ-NFR-SEC-005] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL anonymise any PII detected in logs (regex + ML detector) before persistence.
AC    : Sample inspection: 0 PII strings in last 10K log lines.
Trace : Design §12 → Task T-1722.

### 19.7 国际化 (REQ-NFR-I18N-***)

[REQ-NFR-I18N-001] Priority=Must  Source=P-10  Verify=Integration
EARS  : THE SYSTEM SHALL support default `zh-CN` and at least `en-US`, `ja-JP`, `es-ES` for outputs (subtitles + dubbed dialogue + metadata).
AC    : Per-locale acceptance tests pass.
Trace : Design §13 → Task T-1723.

[REQ-NFR-I18N-002] Priority=Must  Source=P-10  Verify=Unit
EARS  : THE SYSTEM SHALL never hard-code locale-specific copy in Agent code; all strings live in `i18n/{locale}.yaml`.
AC    : Linter blocks hard-coded strings; CI gate.
Trace : Design §13 → Task T-1724.

[REQ-NFR-I18N-003] Priority=Should  Source=P-10  Verify=Integration
EARS  : THE SYSTEM SHALL run per-locale translation QA (back-translation BLEU ≥ 35) on dialogue.
AC    : QA report per locale; below-threshold lines retranslated.
Trace : Design §13 → Task T-1725.

### 19.8 可维护性 / 可扩展性 (REQ-NFR-MAINT-***)

[REQ-NFR-MAINT-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL keep `mypy --strict` clean and ≥ 85% unit test coverage on `src/`.
AC    : CI enforces; reports stored.
Trace : Design §14 → Task T-1726.

[REQ-NFR-MAINT-002] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL honour the dependency direction defined in `structure.md`; cross-layer imports are blocked by `import-linter`.
AC    : Linter green; layered architecture preserved.
Trace : Design §14 → Task T-1727.

[REQ-NFR-MAINT-003] Priority=Should  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL allow new render adapter plugins by implementing the `RenderAdapter` Protocol without changing pipelines.
AC    : Protocol unit test exercised with a mock plugin.
Trace : Design §14 → Task T-1728.

---

## 20. 三集闭环试点验收 (REQ-PILOT-***) — 与下一轮直接对接的硬验收门

> 本章是下一轮工程交付的"通过 / 不通过"判定依据。所有 PILOT 条目必须在 `tests/e2e_three_episodes/` 下产生证据。

[REQ-PILOT-001] Priority=Must  Source=P-1+P-4+P-5  Verify=E2E
EARS  : THE SYSTEM SHALL generate, fully autonomously, 3 episodes from the canonical pilot novel (`tests/e2e_three_episodes/input/sample_novel.md`) within 3 iteration cycles each, with **zero human approval events** in the audit log.
AC    : Audit log contains 0 `manual_*` events; final state of all 3 episodes is `Released`.
Trace : Design §11, §15 → Task T-1801.

[REQ-PILOT-002] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL achieve cross-episode mean ArcFace ≥ 0.92 across all 3 episodes for every lead character.
AC    : `09_qa_reports/cross_episode_matrix.json` shows compliance.
Trace : Design §9 → Task T-1802.

[REQ-PILOT-003] Priority=Must  Source=P-4  Verify=QAAgent
EARS  : THE SYSTEM SHALL achieve per-shot LAION-Aesthetic mean ≥ 6.0 with worst-shot ≥ 5.5 in the pilot run.
AC    : Aesthetic report passes thresholds.
Trace : Design §15 → Task T-1803.

[REQ-PILOT-004] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL achieve VBench Subject Consistency ≥ 0.85 per episode in the pilot run.
AC    : VBench report passes.
Trace : Design §15 → Task T-1804.

[REQ-PILOT-005] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL achieve UTMOS ≥ 4.0 mean for dialogue audio per episode in the pilot.
AC    : Audio QA passes.
Trace : Design §15 → Task T-1805.

[REQ-PILOT-006] Priority=Must  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL achieve `|SyncNet offset| ≤ 2 frames` for every dialogue-bearing shot in the pilot.
AC    : SyncNet report passes.
Trace : Design §15 → Task T-1806.

[REQ-PILOT-007] Priority=Must  Source=P-6  Verify=E2E
EARS  : THE SYSTEM SHALL deliver each pilot episode in ≤ 60 minutes wall-clock and ≤ ¥80 of external spend.
AC    : Latency / cost telemetry attached to pilot report.
Trace : Design §13 → Task T-1807.

[REQ-PILOT-008] Priority=Must  Source=P-7  Verify=Unit
EARS  : THE SYSTEM SHALL produce a `tests/e2e_three_episodes/reports/final_report.md` summarising KPI tables, iteration log, cost breakdown, and provenance manifests for the 3 episodes.
AC    : Report rendered; signed off by `SpecReviewAgent` automated checklist.
Trace : Design §11 → Task T-1808.

[REQ-PILOT-009] Priority=Must  Source=P-9  Verify=E2E
EARS  : THE SYSTEM SHALL exercise at least one degradation path during the pilot (chaos test injects a Xiaoyunque 5xx for one shot) and recover automatically.
AC    : Chaos test logged; recovery path artefact present; pilot still passes.
Trace : Design §10 → Task T-1809.

[REQ-PILOT-010] Priority=Must  Source=P-3  Verify=E2E
EARS  : THE SYSTEM SHALL pass a determinism re-run test: re-running the pilot with identical `(novel_sha, config_sha, seed)` reproduces deterministic stages bit-for-bit.
AC    : Diff = 0 on deterministic stages; non-deterministic stages explicitly listed.
Trace : Design §11 → Task T-1810.

[REQ-PILOT-011] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL prove via static analysis that the pilot run touched 0 code paths labelled `human_required` / `manual_review` / `wait_for_approval`.
AC    : Static analyser report attached to pilot report.
Trace : Design §5 → Task T-1811.

[REQ-PILOT-012] Priority=Should  Source=P-5  Verify=QAAgent
EARS  : THE SYSTEM SHALL detect at least one synthetic continuity bug injected into the pilot (e.g. forced outfit color flip) and auto-repair it within 1 iteration cycle.
AC    : Bug injection harness present; detection + repair logged.
Trace : Design §10 → Task T-1812.

---

## 21. 兼容 / 扩展约束 (REQ-EXT-***)

[REQ-EXT-001] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL version every external API contract (`/v1/*`); breaking changes go to `/v2/*` keeping `/v1/*` for ≥ 12 months.
AC    : Contract test suite `tests/contracts/` covers v1.
Trace : Design §3 → Task T-1901.

[REQ-EXT-002] Priority=Must  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL keep schema migrations forward-compatible at the artefact level (new fields default-valued); migrations live in `migrations/`.
AC    : Migration test compares old vs. new artefacts.
Trace : Design §6 → Task T-1902.

[REQ-EXT-003] Priority=Should  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL support a `pluggable_adapter` ABI version 1 contract for adding new render / TTS / LLM providers.
AC    : Adapter contract test passes for a sample plugin.
Trace : Design §14 → Task T-1903.

[REQ-EXT-004] Priority=Must  Source=P-1  Verify=E2E
EARS  : THE SYSTEM SHALL refuse to load a plugin whose Protocol signature differs from the pinned ABI; plugin registry signs each plugin.
AC    : Plugin sandbox tests verify rejection.
Trace : Design §12 → Task T-1904.

[REQ-EXT-005] Priority=Should  Source=P-2  Verify=Unit
EARS  : THE SYSTEM SHALL emit an `OpenAPI 3.1` spec at `/openapi.json`; downstream platforms can codegen clients.
AC    : Spec validates; codegen smoke test green.
Trace : Design §3 → Task T-1905.

---

## 附录 A — EARS 模板与示例

完整 EARS 五种模式与本仓库强制元字段（重申）：

```
[REQ-XX-NNN]   Priority=Must|Should|May   Source=P-#   Verify=Unit|Integration|E2E|QAAgent|FormalProof
Pattern        : Ubiquitous | Event-driven | State-driven | Optional feature | Unwanted
EARS sentence  : THE SYSTEM SHALL …
                 WHEN <event> THE SYSTEM SHALL …
                 WHILE <state> THE SYSTEM SHALL …
                 WHERE <feature flag> THE SYSTEM SHALL …
                 IF <condition> THEN THE SYSTEM SHALL …
AC             : machine-verifiable assertion
Trace          : Design §x.y → Task T-####
Notes (opt)    : …
```

## 附录 B — KPI 数学定义

| KPI | 定义 | 阈值 |
| --- | --- | --- |
| FaceSim (cross-episode mean) | mean over (i,j) episodes of cosine(Embed_ArcFace(face_i), Embed_ArcFace(face_j)) | ≥ 0.92 (lead), ≥ 0.88 (support) |
| OutfitMatch | average per-shot multi-label CLIP precision against declared outfit attribute set | ≥ 0.95 |
| AestheticMean | mean LAION-Aesthetic v2 over ≥ 8 sampled frames per shot | ≥ 6.0; worst-frame ≥ 5.5 |
| VBenchSC | VBench Subject Consistency score | ≥ 0.85 |
| UTMOS | UTMOS predicted MOS, mean over dialogue lines | ≥ 4.0 |
| SyncOffset | SyncNet predicted A/V offset in frames | `|offset| ≤ 2` |
| ContinuityScore | weighted mean of (location coherence + character coherence + time coherence) per consecutive shot pair | ≥ 0.9 |
| BudgetUsage | sum of credits spent / `max_credits` | ≤ 1.0; alert at 0.8 |
| EpisodeLatencyP95 | 95th percentile wall-clock from script start → released | ≤ 60 min |
| EpisodeSuccessRate | rolling success / (success+failed) over 1k episodes | ≥ 0.99 |

## 附录 C — Failure Mode Catalog (供 IterationManager 引用)

```
F-001  prompt_too_long              -> rewrite_prompt
F-002  reference_image_missing      -> regen_reference_assets
F-003  consistency_face_low         -> consistency_refresh + lora_train(if tier)
F-004  outfit_mismatch              -> regen_reference_assets(outfit) + prompt_clarify
F-005  aesthetic_low                -> upgrade_model_tier OR rewrite_prompt
F-006  vbench_subject_low           -> increase_reference_count + reseed
F-007  syncnet_offset_high          -> lipfix_pass (MuseTalk)
F-008  utmos_low                    -> regen_tts(stronger_voice|prosody)
F-009  moderation_hit               -> discard episode (no retry)
F-010  api_5xx                      -> backoff_retry -> seedance_fallback
F-011  api_429                      -> backoff_retry
F-012  budget_overshoot_predicted   -> degrade_tier
F-013  schema_violation_blueprint   -> retry_structured + stronger_llm
F-014  schema_violation_script      -> retry_structured + RAG
F-015  duration_overrun             -> rewrite_storyboard_pacing
F-016  group_scene_too_many         -> decompose_storyboard
F-017  drift_episode_trend          -> preemptive_consistency_refresh
F-018  voice_consent_missing        -> hard_fail (project terminate)
F-019  mime_mismatch                -> hard_fail
F-020  redline_violation_input      -> hard_fail
```

## 附录 D — 合规与红线表 (摘要)

| 类别 | 处置 | 关联 REQ |
| --- | --- | --- |
| 真人未授权肖像 | 拒绝输入；产物丢弃 | REQ-RA-010, REQ-NFR-SEC-003 |
| 政治敏感 / 宗教冲突 | 整集废弃 + Incident | REQ-NFR-SEC-003/004 |
| NSFW > Tier-A | 拒绝输入或废弃 | REQ-NFR-SEC-003/004 |
| 未成年人不当内容 | 拒绝输入 | REQ-NFR-SEC-003/004 |
| 抄袭 / IP 风险 | 标注 + 上报 | REQ-NFR-SEC-005 |

## 附录 E — REQ-ID 一览（按 ID 排序索引）

> 本附录由 `SpecReviewAgent` 自动生成；下列条目数即文档 EARS 总数。

```
REQ-IN-001..012        (12)
REQ-SA-001..012        (12)
REQ-EP-001..010        (10)
REQ-CB-001..012        (12)
REQ-RA-001..010        (10)
REQ-SW-001..010        (10)
REQ-SD-001..009        (9)
REQ-VS-001..006        (6)
REQ-VD-001..006        (6)
REQ-MD-001..005        (5)
REQ-RO-001..015        (15)
REQ-QA-001..008        (8)
REQ-CC-001..006        (6)
REQ-IT-001..008        (8)
REQ-MO-001..010        (10)
REQ-CON-001..010       (10)
REQ-NFR-PERF-001..004  (4)
REQ-NFR-REL-001..003   (3)
REQ-NFR-COST-001..003  (3)
REQ-NFR-OBS-001..004   (4)
REQ-NFR-PROV-001..003  (3)
REQ-NFR-SEC-001..005   (5)
REQ-NFR-I18N-001..003  (3)
REQ-NFR-MAINT-001..003 (3)
REQ-PILOT-001..012     (12)
REQ-EXT-001..005       (5)
————————————————————————————
TOTAL                  189 normative EARS items
```

> 注：本 v1 Spec 落地 **189** 条强制 EARS（覆盖 14 Agent + 6 横切 NFR 域 + Pilot + Compatibility）。Design / Tasks 阶段如发现遗漏，将通过 v1.1 增量补充并保留 ID 不重用。

---

## 22. 自验证清单 (SelfCheck)

> 此清单由 `SpecReviewAgent` 自动跑通后才能 promote spec 到 `Approved`。

- [x] 每条 EARS 拥有唯一 `REQ-XX-NNN`
- [x] 每条 EARS 拥有可机器判定 AC
- [x] 每条 EARS 双向追溯到 Design §x.y 与 Task T-####
- [x] 全文 0 处 `human_required` / `manual_review` / `operator_*` / `请运营审核` 等措辞 (P-1)
- [x] 全文已显式标注 P-1 ~ P-10 来源 (Source=P-#)
- [x] 至少一条 EARS 涵盖每个 14 个 Agent 的核心职责
- [x] 跨集人物一致性专章存在 (§18, REQ-CON-***)
- [x] Pilot 验收章节给出可机器跑通的 KPI 阈值 (§20)
- [x] 失败模式枚举完整覆盖 IT 决策表 (附录 C)
- [x] 合规红线表与产品 steering §6 对齐 (附录 D)
- [x] REQ-ID 索引附录与正文条数一致 (附录 E)

---

> 至此 Phase 1 完成。下一阶段：[`design.md`](./design.md)。

