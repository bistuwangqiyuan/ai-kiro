# AI 漫剧 Autopilot · v2.0 (need.md V3.0 全栈升级)

> 输入一本小说 → 自动产出多集人物一致漫剧视频 + 抖音/快手/视频号导出包 + 封面 + 文案。
> **v2.0 全栈升级** = 双模式入口（Simple/Pro）+ 11 大新服务（情绪库/动作库/换装/场景复用/9-25 宫格/风格迁移/同人衍生/BGM 卡点/多平台导出/模板化制作）+ Python 量化白皮书（10 模型 / seed=20260526 / byte-identical）+ 三集 mock 反向校准。
> **v4 底层** = 小云雀 Agent 2.0「有参考」核心引擎 + 5 层外壳（Claude Opus 编剧 + Seedream/Jimeng 资产 + Doubao VLM 质检 + fal.ai 脸锁 + ElevenLabs 后期）+ 火山引擎云原生。

## v2.0 关键能力

| 模块 | 入口 | 单元测试 | 关键锚定 |
| --- | --- | --- | --- |
| 双模式路由 | `manhuaju.api.mode_router` + `web/{simple,pro}.html` | `tests/unit/test_mode_router.py` (9) | `config/modes.yaml` |
| 9-25 宫格分镜 | `services.storyboard_grid` + `services.grid_renderer` | `tests/unit/test_grid.py` (14) | 动态格数 + 序号 + SHA |
| 角色情绪库 runtime | `services.emotion_library` + `services.emotion_injection` | `tests/unit/test_emotion_lib.py` (13) | ArcFace ≥ 0.94 |
| 角色动作库 runtime | `services.action_library` + `adapters.pose.{mock,real_dwpose}_adapter` | `tests/unit/test_action_lib.py` (13) | reuse cos ≥ 0.90 |
| 角色换肤 | `services.outfit_change` + `services.season_dynasty_matcher` | `tests/unit/test_outfit_change.py` (12) | season×dynasty 100% |
| 场景库 embedding 复用 | `services.scene_library` + `adapters.embedding.scene_index_adapter` | `tests/unit/test_scene_library.py` (12) | 相似度 ≥ 0.85 |
| 风格迁移 | `services.style_transfer` + `adapters.styletransfer.{mock,real_seedream_styletx}_adapter` | `tests/unit/test_style_transfer.py` (10) | 4 styles + 面部锁 |
| 同人衍生 ingest | `services.transmedia_ingest` + `services.keyframe_extractor` | `tests/unit/test_transmedia.py` (13) | license gate |
| BGM 卡点剪辑 | `services.music_alignment` + `services.auto_cut` | `tests/unit/test_auto_cut.py` (11) | 节奏 ±0.5s |
| 多平台导出 + 水印 + 文案 | `services.{distribution_pack,watermark,copy_style_router}` | `tests/unit/test_distribution_pack.py` (10) | 5 平台矩阵 |
| 模板化制作 | `services.template_engine` + `config/templates/*.yaml` | `tests/unit/test_template_engine.py` (12) | 3 题材模板 |
| Pipeline 集成 | `pipelines.v2_enrichment` (pre/postflight) | `tests/integration/test_v2_enrichment.py` (5) | import-linter green |
| 三集回归校准 | `research.whitepaper.scripts.calibrate_from_pilot` | `tests/e2e_three_episodes/test_post_calibration.py` (7) | 95% CI 上界 |

## v2.0 一键复现量化白皮书

```bash
# 所有数字（成本 ≤ ¥80 / 单集 P95 ≤ 60min / ArcFace ≥ 0.92 / 8 集/小时 / 7 维通过率）由模型反推
SEED=20260526 python -m research.whitepaper.scripts.run_all
pytest research/whitepaper/tests/ -q  # byte-identical 检查
```

输出：

* `research/whitepaper/data/computed/*.json` — 锚定 KPI（被 `requirements.md §23` / `design.md §13` import）
* `research/whitepaper/figures/*.png` — 10 张图
* `research/whitepaper/notebooks/*.ipynb` — 10 个 notebook

## v2.0 三集 mock 反向校准

```bash
pytest tests/e2e_three_episodes -q
# 跑完后会写 tests/e2e_three_episodes/reports/{kpi_summary.json, final_report.md}
# test_post_calibration.py 会自动：构造 telemetry → 调 calibrate_from_pilot.py → 断言 95% CI 上界
```

---

| 项目 | 数值 |
| --- | --- |
| 核心生产引擎 | 火山小云雀 Agent 2.0 (`skylark_video_agent_v2_with_ref`) |
| 编剧大脑 | Anthropic Claude Opus 4 (256K context) |
| 角色资产 | Seedream 5.0 × 8 + Jimeng 4.6 × 6 = 14 张/角色 |
| 多模态质检 | Doubao Seed 1.6 VLM (7 维：结构/风格/细节/清晰/色彩/无崩坏/意图) |
| 单镜锁脸重生 | fal.ai Wan 2.7 FLF |
| 后期音乐 / 音效 | ElevenLabs Music + Sound Generation (版权干净) |
| 字幕 | 自渲染 ASS（思源宋体 / 思源黑体，绕开 AI 字层乱码） |
| 跨集一致性 | InsightFace ArcFace ≥ 0.92 (KPI) |
| 单集成本目标 | ¥60 软目标 / ¥80 硬上限 |
| 单集时长上限 | 30 min (live) / 40 min (hard) |
| 月产能目标 | ≥ 1500 集 |
| 部署 | Volcengine VKE (Helm) + TOS + CDN + RDS PostgreSQL + KMS |

## 0. 一键 v4

```bash
# 1) 装依赖（live + 一致性 + 可观测）
pip install -e ".[live,consistency,observe]"

# 2) 配 Key
cp .env.example .env
# 至少填：ANTHROPIC_API_KEY / VOLCENGINE_VISUAL_AK/SK / VOLCENGINE_ARK_API_KEY /
#         VOLCENGINE_TOS_AK/SK/BUCKET / DASHSCOPE_API_KEY / ELEVENLABS_API_KEY / FAL_KEY

# 3) 烟测所有 Key（红色 ★ 必须全绿）
python -m scripts.smoke_keys --strict

# 4) 启 API（含 Web 控制台）
uvicorn manhuaju.api.app:app --host 0.0.0.0 --port 8080
open http://localhost:8080/                 # 控制台

# 5) 一键生 3 集
curl -X POST http://localhost:8080/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "novel_text": "她重生回到了那一年的春天……",
    "episode_count": 3,
    "genre": "ancient",
    "episode_duration_s": 75,
    "platforms": ["douyin", "kuaishou", "weixin"]
  }'

# 6) 部署到火山 VKE
helm upgrade --install manhuaju ./deploy/helm/manhuaju \
  --namespace manhuaju --create-namespace \
  --set ingress.host=api.manhuaju.example.com \
  --set image.tag=0.4.0
```

完整云部署指南：[`deploy/README.md`](deploy/README.md)。

## v4 架构（5 层外壳 + 4 道一致性防线）

```
┌──── Shell 1 编剧大脑（Anthropic Claude Opus 4） ────────────────────────────┐
│  novel → extract_events → write_episodes → format_for_xiaoyunque           │
│  ★ 防线 1：每集开头必出完整人物设定块 + 场景设定块                          │
└─────────────────────────────────────────────────────────────────────────────┘
┌──── Shell 2 角色与场景资产库（Seedream 5.0 + Jimeng 4.6） ──────────────────┐
│  每个主角 14 张参考图：8 张多角度（正/45/侧/背 + 4 表情）+ 6 张姿态/服装变体 │
│  每个场景 6 张：近/中/远 × 昼/夜。全部入 TOS 拿 24h 预签名 URL              │
│  ★ 防线 2：同一组 reference_images 全集复用（CharacterAssetStore）         │
└─────────────────────────────────────────────────────────────────────────────┘
┌──── Shell 3 ★ 小云雀 Agent 2.0「有参考」（核心生产肌肉） ────────────────────┐
│  per-episode 整集 submit（75s 一次到位）                                    │
│  reference_weight=0.85 强约束 ★ 防线 3                                       │
└─────────────────────────────────────────────────────────────────────────────┘
┌──── Shell 4 质检与重生（Doubao Seed 1.6 VLM + fal.ai Wan 2.7 FLF） ─────────┐
│  逐镜抽 5 帧 → 7 维 VLM 评分 → 命中 issue.type → 5 路修复路由               │
│   face_drift  → wanflf   (FLF 锁脸重生)                                     │
│   axis_violation / limb_distortion → seedance (单镜重生)                    │
│   text_garbled  → overlay (ASS 字幕烧入，去 AI 字层)                       │
│   style_offshift / intent_mismatch → xiaoyunque (强化 style_ref + prompt)   │
│  跨集 InsightFace ArcFace 矩阵 ★ 防线 4                                     │
└─────────────────────────────────────────────────────────────────────────────┘
┌──── Shell 5 后期（ElevenLabs + ASS + 三平台导出） ──────────────────────────┐
│  Music API (75s 单集 BGM) + Sound Gen (音效) + 自渲染 ASS 字幕 + 封面        │
│  → 抖音 / 快手 / 视频号 ffmpeg 转码 + 平台文案 + 多格式（短/长/PDF）         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## v4 API 端点（控制台同步）

```text
GET  /health                            # 提供 provider 能力图（masked Key）+ fast_path_ready
POST /v1/projects                       # 一键开剧
GET  /v1/projects                       # 项目列表
POST /v1/novels                         # 小说生成 / 续写 / 风格迁移
POST /v1/batch/jobs                     # 批量任务
POST /v1/batch/schedules                # 定时任务 (cron)
GET  /v1/genres /v1/platforms /v1/emotions /v1/actions    # 控制台读取预设
GET  /v1/kpi                            # 实时 KPI 阈值
GET  /v1/versions/{project_id}          # 版本回滚
GET  /                                  # Web 控制台 (web/index.html)
```

## v4 KPI（八条）

| ID | 项 | 阈值 |
| --- | --- | --- |
| REQ-V4-001 | 跨集 ArcFace | ≥ 0.92 |
| REQ-V4-002 | VLM 7 维 mean | ≥ 8.0 |
| REQ-V4-003 | 单集端到端 | ≤ 30 min |
| REQ-V4-004 | 单集 RMB | ≤ ¥60 软 / ¥80 硬 |
| REQ-V4-005 | 月产能 | ≥ 1500 集 |
| REQ-V4-006 | AI 字层乱码率 | = 0 |
| REQ-V4-007 | 高敏感词命中 | = 0 |
| REQ-V4-008 | 3 平台导出 + 封面 + 文案 | 必齐 |

完整阈值表见 [`config/kpi.yaml`](config/kpi.yaml)。

---

## 历史里程碑

> 以下保留 M2 / M3 / v2 历史架构信息，方便对比。



---

## 0. 一句话定位

输入一篇小说 → 自动产出 3 集人物一致的漫剧视频 + 平台导出包 + 12 KPI 验收报告，**默认 Autopilot 零人工**；可选 `workflow.mode=supervised` 在 Step 6 启用 ReviewGate。

### 1.5 六步商业工作流（v2）

| 步骤 | 阶段 | 主要 Agent / 模块 |
| --- | --- | --- |
| 1 | 剧本分析 | StoryArchitect + EpisodePlanner + DialogueOptimizer |
| 2 | 人物/场景/道具资产 | CharacterBible + Reference/Scene/Prop Asset |
| 3 | 分镜提示词 | ScriptWriter + StoryboardDirector |
| 4 | 抽卡生视频 | RenderOrchestrator（N 候选 + i2v refs） |
| 5 | 粗剪 | `pipelines/rough_cut.py` |
| 6 | 精剪审核 | `pipelines/fine_cut.py` + 7 维 QA + IterationManager |
| + | 分发 | DistributionAgent → 抖音/快手 MP4 + cover + copy |

配置见 [`config/system.yaml`](config/system.yaml) 的 `workflow` / `distribution` 块；画风预设见 [`config/style-presets.yaml`](config/style-presets.yaml)（6 套）。

### 1.6 FastAPI 云 API（M4 骨架）

```bash
pip install -e .
uvicorn manhuaju.api.app:app --host 0.0.0.0 --port 8080
curl http://localhost:8080/health
curl -X POST http://localhost:8080/v1/projects -H "Content-Type: application/json" \
  -d '{"novel_text":"样例小说正文……","episode_count":3}'
```

Docker / Railway：

```bash
docker compose up --build
# Railway: 连接仓库后读取 railway.toml，设置 MANHUAJU_API_DATA=/data
```

详见 [`.env.example`](.env.example)、[`Dockerfile`](Dockerfile)、[`docs/requirements_traceability_matrix.md`](docs/requirements_traceability_matrix.md)。


---

## 1. 快速开始

### 1.1 环境

- Python 3.11+（开发使用 3.13）
- ffmpeg 7.x+（windows 已使用 `8.1.1-full_build-www.gyan.dev` 验证）
- Pillow / numpy / pydantic v2 / PyYAML / pytest（详见 [`pyproject.toml`](pyproject.toml)）

```bash
python -m pip install -e .[dev]
```

### 1.2 跑 3 集 Pilot

```bash
python -m scripts.run_pilot \
    --novel  tests/e2e_three_episodes/input/sample_novel.md \
    --config tests/e2e_three_episodes/input/pilot_config.yaml \
    --out    tests/e2e_three_episodes/output \
    --reports tests/e2e_three_episodes/reports
```

产物：

- `tests/e2e_three_episodes/output/episodes/ep01.mp4`、`ep02.mp4`、`ep03.mp4`（真实可播 H.264 MP4）
- `tests/e2e_three_episodes/reports/final_report.md`（12 条 Pilot REQ 评分表）
- `tests/e2e_three_episodes/reports/kpi_summary.json`
- `tests/e2e_three_episodes/reports/iteration_log.md`

### 1.3 跑全部测试（M2 默认）

```bash
pytest tests/unit -q                      # 80 个单测
pytest tests/e2e_three_episodes -q        # 23 个 e2e 断言（一次 e2e 共享会话级 fixture）
python tools/lint/forbidden_terms.py      # 0 命中
python scripts/build_traceability_matrix.py  # 0 孤儿
```

### 1.4 跑 M3 Live Pilot（消耗真实 API 额度）

需要在 `.env` 中配置至少一个 Provider Key（推荐 `DASHSCOPE_API_KEY`，覆盖 LLM + 视频 + TTS + Embedding 所有路径）。

```powershell
# —— 1 集 smoke（tests/live_one_episode）——
$env:MANHUAJU_LIVE_MODE = "hybrid"   # hybrid | live
$env:PYTHONPATH         = "src"
python -X utf8 -u -m scripts.run_live_pilot

# —— 3 集最小真视频（每集 1×5s WanX，最终成片 <60s/集；tests/live_three_episodes）——
$env:MANHUAJU_LIVE_SUITE = "three"   # 强制开启 per-episode checkpoint
$env:MANHUAJU_LIVE_MODE  = "hybrid"
$env:PYTHONPATH          = "src"
python -X utf8 -u -m scripts.run_live_pilot
# 若中断：保留 output/，下次加 $env:MANHUAJU_LIVE_RESUME = "1" 同一命令续跑

# 可选：视频主通路覆盖 system.yaml（例：字节方舟 Seedance）
# $env:MANHUAJU_VIDEO_PRIMARY = "volcengine_seedance"

# pytest（需先有 reports/ 产物）
$env:MANHUAJU_LIVE_E2E = "1"
pytest tests/live_one_episode -v      # 6 tests
pytest tests/live_three_episodes -v   # 7 tests（需要 ffmpeg/ffprobe 做 <60s 断言）
```

**WanX 说明**：配置里的 `1080p` 表示「广播级意向」；`wanx2.1-t2v-turbo` 仅支持固定 `size` 白名单（**不支持** `1920×1080`），适配器自动映射为允许的最高 16:9（`1280*720`）。详见 `tests/live_three_episodes/reports/` 跑出来的 `final_report.md`。

**安全**：请勿将填好密钥的 `.env` 粘贴到聊天或提交到 Git；若已外泄请立即在各家控制台**轮换**密钥。

---

## 2. 架构

```mermaid
flowchart LR
    Caller["pytest e2e \\ scripts.run_pilot"] --> ProjectFlow[ProjectPipeline]
    ProjectFlow --> StoryArch[StoryArchitectAgent]
    ProjectFlow --> EpPlanner[EpisodePlannerAgent]
    ProjectFlow --> Bible[CharacterBibleAgent]
    ProjectFlow --> Refs[ReferenceAssetAgent]
    ProjectFlow --> Style[VisualStyleAgent]
    ProjectFlow --> EpisodePipe[EpisodePipeline]
    EpisodePipe --> ScriptW[ScriptWriterAgent]
    EpisodePipe --> Storyboard[StoryboardDirectorAgent]
    EpisodePipe --> Render[RenderOrchestratorAgent]
    EpisodePipe --> Voice[VoiceDirectorAgent]
    EpisodePipe --> Music[MusicDirectorAgent]
    EpisodePipe --> QA[QAReviewerAgent]
    EpisodePipe --> Iter[IterationManagerAgent]
    ProjectFlow --> Cont[ContinuityCheckerAgent]
    ProjectFlow --> Master[MasterOrchestratorAgent]

    Render --> Xy[(MockXiaoyunqueAdapter)]
    Render --> Sd[(MockSeedanceAdapter\\fallback)]
    Voice --> Tts[(MockTTSAdapter)]
    Music --> Mu[(MockMusicAdapter)]
    QA   --> Qae[(MockQAEvaluatorAdapter)]
    EpisodePipe --> Postprod[ffmpeg concat / drawtext / loudnorm]
    Postprod --> MP4[(ep0X.mp4)]
    QA --> KPI[services.kpi]
    KPI --> Report[reporting.final_report]
```

14 个 Agent 全部落在 [`src/manhuaju/agents/`](src/manhuaju/agents/)；其行为由 [`src/manhuaju/adapters/`](src/manhuaju/adapters/) 下的 mock 适配器驱动，下游基础设施（事件总线、状态机、provenance 链、预算）位于 [`src/manhuaju/core/`](src/manhuaju/core/)。

---

## 3. 12 条 Pilot 验收门（M2 当前状态）

| ID | 描述 | 当前状态 | 证据 |
| --- | --- | --- | --- |
| REQ-PILOT-001 | 3 集端到端 + 0 个 WaitFor 节点触达 | ✅ | [`tests/.../test_pipeline_e2e.py`](tests/e2e_three_episodes/test_pipeline_e2e.py) |
| REQ-PILOT-002 | 跨集 ArcFace ≥ 0.92（lead） | ✅ | [`test_cross_episode_consistency.py`](tests/e2e_three_episodes/test_cross_episode_consistency.py) |
| REQ-PILOT-003 | LAION-Aesthetic mean ≥ 6.0 / worst ≥ 5.5 | ✅ | [`test_aesthetic.py`](tests/e2e_three_episodes/test_aesthetic.py) |
| REQ-PILOT-004 | VBench Subject Consistency ≥ 0.85 | ✅ | [`test_aesthetic.py`](tests/e2e_three_episodes/test_aesthetic.py) |
| REQ-PILOT-005 | UTMOS mean ≥ 4.0 | ✅ | [`test_audio_quality.py`](tests/e2e_three_episodes/test_audio_quality.py) |
| REQ-PILOT-006 | SyncNet 偏移 ≤ 2 帧 | ✅ | [`test_audio_quality.py`](tests/e2e_three_episodes/test_audio_quality.py) |
| REQ-PILOT-007 | 单集 ≤ 60 min（mock ≤ 5 min）+ ≤ ¥80（mock = 0） | ✅ | [`test_latency_cost.py`](tests/e2e_three_episodes/test_latency_cost.py) |
| REQ-PILOT-008 | `final_report.md` 自动生成 + 内容齐全 | ✅ | [`reports/final_report.md`](tests/e2e_three_episodes/reports/final_report.md) |
| REQ-PILOT-009 | Chaos 注入 5xx 一次仍恢复 | ✅ | [`test_chaos_degradation.py`](tests/e2e_three_episodes/test_chaos_degradation.py) |
| REQ-PILOT-010 | Determinism 重跑 ≥ 95% 阶段 bit-exact | ✅ | [`test_determinism.py`](tests/e2e_three_episodes/test_determinism.py) |
| REQ-PILOT-011 | 0 路径触及禁词（静态 + 运行双证） | ✅ | [`test_no_human_path.py`](tests/e2e_three_episodes/test_no_human_path.py) + [`tools/lint/forbidden_terms.py`](tools/lint/forbidden_terms.py) |
| REQ-PILOT-012 | 注入 outfit 翻色 bug，1 cycle 内自动检出并修复 | ✅ | [`test_bug_injection.py`](tests/e2e_three_episodes/test_bug_injection.py) |

---

## 4. M2 / M3 范围 vs 推迟项

### M2 范围内（已完成）

- Epic 1（工程基线）+ Epic 2（**仅 Mock 适配器**）+ Epic 3（14 个 Agent）+ Epic 4（Pipelines）+ Epic 5（QA + IT）+ Epic 6（配置中心）+ Epic 7（3 集 Pilot）。
- 所有 mock 都产出**真工件**（mp4/wav/png/json），mock 不是固定字符串桩。
- 双层迭代闭环：L1 管线内 IterationManagerAgent + L2 开发期 meta-iter（详见 [`reports/iteration_log.md`](tests/e2e_three_episodes/reports/iteration_log.md)）。

### M3 范围内（已完成）

- **Real LLM 多 Provider 自动降级**：DashScope (qwen-plus) → GLM (glm-4-flash) → Mistral → Groq → DeepSeek → Moonshot → Volcengine。Real-augmented-Mock 模式确保 schema 永远合规。
- **Real Video Generation**：DashScope WanX 2.1 t2v-turbo（首选）+ Volcengine Ark Seedance（备选）+ MockSeedance（最后兜底）。submit/poll + idempotency 完整契约。
- **Real TTS**：DashScope CosyVoice-v1（同步 SDK）+ voice profile 映射 + lipsync 元数据。
- **Real Embedding**：DashScope text-embedding-v3（1024 维 L2 归一化）。
- **Real Moderation**：关键词预过滤 AND LLM-judge（双源审核 ensemble，符合 design §8）。
- **Real QA Proxy**：LLM-as-judge 美学评分 + Mock 形态 (ArcFace/VBench/SyncNet/UTMOS)；纯 LLM 模型可接入处全部接入。
- **AdapterFactory**：单一接入点，按 `mode = mock | live | hybrid` 切换；live 自动启用 graceful fallback；密钥缺失自动降级到 `*-degraded`。
- **CostTracker**：每个 API 调用记录 RMB / 耗时 / 错误，导出 [`live_cost_summary.json`](tests/live_one_episode/reports/live_cost_summary.json)。
- **Live Pilot 验收**：[scripts/run_live_pilot.py](scripts/run_live_pilot.py) 跑 1 集 Live → 12 条 Pilot KPI 全绿，单集 ≤ 60 min，单集 ≤ ¥80。

### M3 推迟到 M4

- K8s/Helm/ArgoCD/Postgres/NATS/Qdrant/Vault/Loki/Tempo/Grafana → M4。M2/M3 用 SQLite/InMemoryEventBus/LocalFS/structlog 接口对等替身。
- 真 ArcFace / CLIP-Aesthetic / VBench / SyncNet / UTMOS GPU 推理服务 → M4（M3 用 LLM-judge + pHash 代理）。

接口定义在 `src/manhuaju/adapters/` 与 `src/manhuaju/core/` 下，M4 替换实现即可，不动 Agent 与 Pipeline。

---

## 5. 设计原则（不变量）

1. **P-1 自动驾驶 / Autopilot Only**：管线中无任何"人工 review/approve"节点；`tools/lint/forbidden_terms.py` 与 `test_no_human_path.py` 双证。
2. **角色一致性优先**：`(char_id, outfit_id)` 锁住 face/outfit palette，跨集 ArcFace ≥ 0.92。
3. **决策表驱动的修复**：F-001..F-030 落在 [`src/manhuaju/core/failure_modes.py`](src/manhuaju/core/failure_modes.py)，50+ 单测覆盖（[`tests/unit/test_phase_e_failure_table.py`](tests/unit/test_phase_e_failure_table.py)）。
4. **Schema First**：17 个 pydantic v2 模型，全部 `extra=forbid` + `frozen=True`（[`src/manhuaju/schemas/__init__.py`](src/manhuaju/schemas/__init__.py)）。
5. **Provenance Chain**：每个工件 hash 入链（[`src/manhuaju/core/provenance.py`](src/manhuaju/core/provenance.py)），任何写入都可重放校验。

---

## 6. 自验证清单（M2 + M3 交付）

### M2（Mock 3 集）

- [x] `python tools/lint/forbidden_terms.py` → 0 命中
- [x] `python scripts/build_traceability_matrix.py` → 0 孤儿
- [x] `ruff check src tests tools scripts` → 0 errors
- [x] `pytest tests/unit -q` → 80 全绿
- [x] `pytest tests/e2e_three_episodes -q` → 23 全绿
- [x] `tests/e2e_three_episodes/output/episodes/ep0{1,2,3}.mp4` 实际存在 + 可播
- [x] `tests/e2e_three_episodes/reports/final_report.md` 12 条 Pilot REQ 全 PASS
- [x] L2 meta-iter 历史 + L1 cycle 汇总写入 `reports/iteration_log.md`

### M3（Live 1 集）

- [x] `.env` 加载 + ProviderRegistry + AdapterFactory 单接入点
- [x] `python -m scripts.run_live_pilot` 一键产出 1 集 mp4 + 全套 reports
- [x] `pytest tests/live_one_episode -v` → 6 全绿（`MANHUAJU_LIVE_E2E=1`）
- [x] 实测预算（最小生产闭环 1 shot × 5s × 720p）：**¥2.5703 / 集**（cap ¥80）、**143.77 s / 集**（cap 3600 s）
- [x] 真调用 18 次：DashScope LLM 8 × + WanX 真视频 8 ×（含 1 × `video.complete`）+ CosyVoice TTS 1 × + QA aesthetic judge 1 ×
- [x] 真视频落盘验证：`output/fs/_renders/ep01_sh001.mp4` = **1005.5 KB**（mock 14 KB 的 70 倍体积，证明走通真 WanX）；最终 `output/episodes/ep01.mp4` 142.7 KB（含字幕/音轨重编码）
- [x] [`tests/live_one_episode/reports/final_report.md`](tests/live_one_episode/reports/final_report.md) 12 条 Pilot KPI 全 PASS（`Threshold.live()` 阈值）
- [x] 任何 provider 401/超时 / WanX `task_status=FAILED` → 自动降级 mock，pipeline 永不阻塞
- [x] WanX prompt 形态修复（meta-iter 9）：从 pipe-separated 改为逗号 fluent 自然语言，FAILED 率从 100% → 0%

### M3+（Live 3 集 · 最小真视频 × 每集 <60s）

- [x] `$env:MANHUAJU_LIVE_SUITE="three"; python -m scripts.run_live_pilot` → 3×`ep0N.mp4` + reports（**~5.5 min**，**~¥7.6** 总成本，2026-05-16 hybrid 实测）
- [x] `pytest tests/live_three_episodes -v` → 7 全绿（`MANHUAJU_LIVE_E2E=1`，ffprobe 断言每集 `<60s`）
- [x] per-episode **`MANHUAJU_LIVE_CHECKPOINT`** + **`MANHUAJU_LIVE_RESUME`** 续跑（见 §1.4）
- [x] `RealQAProxyAdapter.cross_episode_arcface` 与连续性 Agent 签名对齐（3 集起启用跨集矩阵）
- [x] `1080p` 配置意向 → WanX 白名单自动降为 **`1280*720`**，避免 `InvalidParameter`

## 7. 目录速览

```
.kiro/specs/ai-manhuaju-autopilot/   # Spec 三件套（requirements.md / design.md / tasks.md / README.md）
config/                              # 配置中心：system / kpi / redlines / cost / prompts / style-presets
src/manhuaju/
  schemas/__init__.py                # 17 个 pydantic v2 模型
  core/                              # agent_base / event_bus / budget_service / state_machine / checkpoint / storage / seed / failure_modes / provenance
  adapters/                          # llm / render / tts / music / qa / moderation / embedding / db / circuit
  agents/                            # 18 个 Agent (+ DialogueOptimizer / SceneAsset / PropAsset / Distribution)
  pipelines/                         # project_flow / episode_flow / rough_cut / fine_cut / postprod
  services/                          # kpi + seven_dim_qa + distribution
  api/                               # FastAPI /v1/projects
  reporting/                         # final_report 生成器
  utils/                             # canonical_json / paths / logging
scripts/                             # run_pilot / build_traceability_matrix
tools/lint/                          # forbidden_terms 静态扫描器
tests/unit/                          # 80 个单测
tests/e2e_three_episodes/            # M2 mock e2e
tests/live_one_episode/               # M3 live 1 集验收
tests/live_three_episodes/           # M3+ live 3 集真视频 + <60s/集
```

---

## 8. License & 致谢

- 本项目在 `MIT` 协议下开源（见 [`pyproject.toml`](pyproject.toml)）。
- 内置示例小说 [`sample_novel.md`](tests/e2e_three_episodes/input/sample_novel.md) 为本项目原创虚构，无任何现实人物影射。
- 字体回退路径包含 `Microsoft YaHei` 等系统字体；运行环境若缺字体，drawtext caption 会自动降级为不烧字幕的拷贝（pipeline 不会中断）。

> Built with care, no human in the loop. — 漫剧 Autopilot Agents
