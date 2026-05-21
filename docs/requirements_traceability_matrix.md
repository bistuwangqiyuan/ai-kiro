# 新文档 §一–§十二 → 实现映射（REQ 追溯矩阵）

| 新文档章节 | 需求要点 | Agent / 模块 | 测试 |
| --- | --- | --- | --- |
| §一 剧本分析 | 剧情拆解、台词优化 | StoryArchitectAgent, EpisodePlannerAgent, DialogueOptimizerAgent | test_project_pipeline_three_episodes |
| §二 人物道具资产 | 人物/场景/道具参考图 | ReferenceAssetAgent, SceneAssetAgent, PropAssetAgent | test_workflow_v2_assets |
| §三 分镜提示词 | 分镜 + prompt clauses | StoryboardDirectorAgent, video_prompt | test_video_prompt |
| §四 抽卡生视频 | 多候选 + 参考图 i2v | RenderOrchestratorAgent, RealWanXAdapter | test_render_multi_candidate |
| §五 粗剪 | 镜头拼接 + 粗对齐音轨 | pipelines/rough_cut.py | test_rough_fine_cut |
| §六 精剪审核 | 字幕/loudnorm/QA | pipelines/fine_cut.py, seven_dim_qa, QAReviewerAgent | test_seven_dim_qa |
| §七 画风预设 | 古风/甜宠/赛博等 | config/style-presets.yaml, VisualStyleAgent | test_style_presets_count |
| §八 7维 QA | 7 维评分闭环 | services/seven_dim_qa.py, IterationManagerAgent | test_seven_dim_qa |
| §九 分发 | 抖音/快手导出 | DistributionAgent, services/distribution | test_distribution_export |
| §十 人工复核 | 可选 supervised | ReviewGate, API review | tests/supervised/test_review_gate |
| §十一 版本管理 | provenance 链 | ProvenanceStore, iteration cycles | test_project_pipeline_three_episodes |
| §十二 云部署 | FastAPI + Docker + Railway | api/app.py, Dockerfile, railway.toml | test_api_health |

生成命令：`python scripts/build_traceability_matrix.py`
