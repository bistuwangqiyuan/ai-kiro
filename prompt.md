严格按照 kiro spec 工作流，帮我生成世界最高水平效果最好的基于小云雀的小说分集生成多集人物一致的漫剧视频的全自动工作流系统；这个漫剧工作流，不是交给人来执行，是开发软件全自动执行，请修改所有文档；整个流程中没有人，只有ai只有agnet，只有软件，全自动执行，直到视频产出；并对工作流进行三集的最小闭环的测试，修改视频中的问题，直到测试达到要求。一定要追求最高质量，要世界上最高水平的产出，这是正式的对外的世界最高端项目，一定要拿出最高水平，一定一定要拿出最高水平，不管消耗掉多少token都以编制最高水平的商业计划书为目标，不要在乎消耗多少token。
小云雀：https://www.volcengine.com/docs/85621/2359610?lang=zh

@.kiro/specs/ai-manhuaju-autopilot/design.md @.kiro/specs/ai-manhuaju-autopilot/README.md @.kiro/specs/ai-manhuaju-autopilot/requirements.md @.kiro/specs/ai-manhuaju-autopilot/tasks.md 按照设计文档，开发世界最高水平效果最好的基于小云雀的小说分集生成多集人物一致的漫剧视频的全自动工作流系统；这个漫剧工作流，不是交给人来执行，是开发软件全自动执行；整个流程中没有人，只有ai只有agnet，只有软件，全自动执行，直到视频产出；并对工作流进行三集的最小闭环的测试，修改视频中的问题，直到测试达到要求。
一定要追求最高质量，要世界上最高水平的产出，这是正式的对外的世界最高端项目，一定要拿出最高水平，一定一定要拿出最高水平，不管消耗掉多少token都以编制最高水平的商业计划书为目标，不要在乎消耗多少token。
修改程序，api无效时，则替换为其他可用api：例如： Gemini — 400 无效，则替换为其他api, ；程序运行中出现的问题要有记录，例如若有主力模型api额度不足、qps限值、需要充值等，均需给用户提示，但不要阻塞工作流（替换其他可用api），只是提示,以便用户处理；

# ─────────────────────────────────────────────────────────────────────
# API 密钥清单结构（实际值脱敏，真实值见本地 .env，不入仓库）
# ─────────────────────────────────────────────────────────────────────

# --- 火山引擎（小云雀 / Seedance / Seedream / 即梦 / OmniHuman / 豆包视觉） ---
VOLC_AK=***REDACTED***
VOLC_SK=***REDACTED***
VOLC_REGION=cn-north-1

# --- 火山方舟 (Ark Runtime: 豆包 LLM / Seed 1.6 Vision / TTS) ---
VOLCENGINE_API_KEY=***REDACTED***
ARK_API_KEY=***REDACTED***
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# --- 豆包 TTS（语音合成 + ICL V3 声音复刻） ---
DOUBAO_TTS_APP_ID=***REDACTED***
DOUBAO_TTS_ACCESS_TOKEN=***REDACTED***
DOUBAO_TTS_CLUSTER=volcano_icl_v3

# --- Anthropic Claude Opus 4.7 (可选代理) ---
ANTHROPIC_API_KEY=***REDACTED***
ANTHROPIC_BASE_URL=***REDACTED-OR-EMPTY-FOR-OFFICIAL***
ANTHROPIC_AUTH_TOKEN=***REDACTED-IF-USING-PROXY***
ANTHROPIC_MODEL=claude-opus-4-7

# --- DeepSeek V4-Pro ---
DEEPSEEK_API_KEY=***REDACTED***
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro

# --- OpenAI Sora 2 Pro + GPT-4o Vision ---
OPENAI_API_KEY=***REDACTED***
OPENAI_SORA_MODEL=sora-2-pro
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# ===== 其他 API 密钥（备用，按优先级失败转移） =====

# --- Google Gemini 3 Pro Video + Veo 3.1 ---
GOOGLE_API_KEY=***REDACTED***
GEMINI_VIDEO_MODEL=gemini-3-pro-video
VEO_MODEL=veo-3.1-fast

# --- MiniMax (Speech 02 HD + 视频) ---
MINIMAX_API_KEY=***REDACTED***
MINIMAX_GROUP_ID=***REDACTED***
MINIMAX_TTS_MODEL=speech-02-hd

# --- Groq / Mistral Pixtral / 智谱 GLM-4V ---
GROQ_API_KEY=***REDACTED***
MISTRAL_API_KEY=***REDACTED***
GLM_API_KEY=***REDACTED***

# ===== OpenAI 兼容的中文 LLM/VLM 备选 =====
DASHSCOPE_API_KEY=***REDACTED***
MOONSHOT_API_KEY=***REDACTED***
TONGYI_API_KEY=***REDACTED***
TENGCENT_API_KEY=***REDACTED***
SPARK_API_KEY=***REDACTED***
DOUBAO_API_KEY=***REDACTED***
XAI_API_KEY=***REDACTED***
ELEVENLABS_API_KEY=***REDACTED***

# --- 对象存储（火山 TOS） ---
TOS_ACCESS_KEY=***REDACTED***
TOS_SECRET_KEY=***REDACTED***
TOS_ENDPOINT=https://tos-cn-beijing.volces.com
TOS_BUCKET=***REDACTED***

# ===== 多模型自动切换（按优先级依次尝试） =====
# VLM_PROVIDER_CHAIN 默认: anthropic-claude → google-gemini → doubao-vision → mistral-pixtral → glm-4v → openai-gpt4o → moonshot-kimi → xai-grok → dashscope-qwen

# ─────────────────────────────────────────────────────────────────────
# 多轮迭代研究 prompt（10 轮 + 10 轮共 20 轮）
# ─────────────────────────────────────────────────────────────────────

全面研究本项目，检查是否实现了世界最高水平的技术方案（核心技术点为智能生视频 Agent —— Seedance 2.0 fast 720p 有参考 （即「小云雀 Agent 2.0」）），进行深入调研，研究提升办法，进行优化提升并测试，目标达到99分（百分制），也就是达到世界最顶级 ，以 novel-无限恐怖.md 的开篇第一章的三集 15 秒左右漫剧的真实小云雀核心生成为测试样例，具体剧集内容，按照实际工业级生产确定；持续进行 10 轮这样的研究和优化循环迭代，直到达到 99 分；

# 测试素材来源说明（不入库）
# 用户在对话中提供了《无限恐怖》（流浪蛤蟆 著）第一集第一章原文作为改编参考输入。
# 该原文文本受版权保护，仅用于本项目本地改编输入，不入版本库。
# 派生内容（视频画面、分镜 prompt、Skylark 请求体）均为原创视觉描述，不含原文逐字。
# 如需复现实验，请将原文存入 data/novel-无限恐怖-ch01-source.md（已在 .gitignore 中）。
