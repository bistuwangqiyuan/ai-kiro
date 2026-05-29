"""Live-mode provider configuration and `.env` ingestion (v4).

Loads API keys from `.env` once and exposes them as immutable, masked-friendly
strings. All callers MUST go through `get_provider_settings()` rather than
reading os.environ directly so we have a single point of redaction in logs.

v4 expansions:
- Anthropic Claude Opus 4 (Shell 1 编剧大脑)
- Volcengine Visual Service AK/SK (Shell 2 Seedream/Jimeng + Shell 3 小云雀 + Shell 4 Doubao VLM)
- Volcengine TOS (对象存储 — 给小云雀「有参考」接口暴露图片 URL)
- ElevenLabs (Shell 5 BGM/SFX, 版权干净)
- fal.ai (Shell 4 Wan 2.7 FLF 单镜锁脸)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from manhuaju.utils.paths import project_root


def _load_env_once() -> None:
    env_path = project_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_env_once()


def _redact(s: str | None) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


@dataclass(frozen=True)
class ProviderEndpoint:
    """A single OpenAI-compatible LLM endpoint configuration."""

    name: str
    api_key: str
    base_url: str
    default_model: str
    timeout_s: float = 60.0
    json_mode: bool = True
    rpm: int = 60
    enabled: bool = True
    kind: str = "openai_compatible"   # openai_compatible | anthropic_native

    @property
    def masked_key(self) -> str:
        return _redact(self.api_key)


@dataclass(frozen=True)
class TOSSettings:
    """火山 TOS 对象存储配置。"""

    ak: str = ""
    sk: str = ""
    region: str = "cn-beijing"
    endpoint: str = "tos-cn-beijing.volces.com"
    bucket: str = "manhuaju-assets"
    cdn_domain: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.ak and self.sk and self.bucket)

    def public_url(self, key: str) -> str:
        """Return CDN URL when configured, else direct TOS URL."""
        if self.cdn_domain:
            return f"https://{self.cdn_domain.rstrip('/')}/{key.lstrip('/')}"
        return f"https://{self.bucket}.{self.endpoint}/{key.lstrip('/')}"


@dataclass(frozen=True)
class ProviderSettings:
    """All provider keys + endpoints loaded from .env (v4)."""

    llm_endpoints: tuple[ProviderEndpoint, ...] = field(default_factory=tuple)

    # ---- 火山系 ----
    volcengine_ark_key: str = ""
    volcengine_visual_ak: str = ""
    volcengine_visual_sk: str = ""
    volcengine_visual_region: str = "cn-north-1"
    # NOTE: the 小云雀短剧 Agent models (skylark_*) require separate account
    # activation; on accounts without it the Visual API returns 50200
    # "req_key not supported" and every shot silently degraded to mock. The
    # 即梦 (Jimeng) general video models are available on the standard Visual
    # plan, so they are the default. Override via VOLCENGINE_XIAOYUNQUE_REQ_KEY.
    xiaoyunque_req_key: str = "jimeng_t2v_v30"
    duanju_req_key: str = "jimeng_t2v_v30"
    seedream_req_key: str = "seedream_5_0_t2i"
    jimeng_req_key: str = "jimeng_high_aes_general_v46"

    # ---- 阿里 / 海外 ----
    dashscope_key: str = ""
    anthropic_key: str = ""
    elevenlabs_key: str = ""
    fal_key: str = ""
    gemini_key: str = ""
    xai_key: str = ""
    openai_key: str = ""

    # ---- 对象存储 ----
    tos: TOSSettings = field(default_factory=TOSSettings)

    # ---- 数据库 ----
    postgres_dsn: str = ""

    # ---- 全国产化开关 ----
    domestic_only: bool = True

    # ===== 能力判定 =====
    @property
    def has_any_llm(self) -> bool:
        return any(e.enabled and e.api_key for e in self.llm_endpoints)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_key) and not self.domestic_only

    @property
    def has_xiaoyunque(self) -> bool:
        return bool(self.volcengine_visual_ak and self.volcengine_visual_sk)

    @property
    def has_seedream(self) -> bool:
        return self.has_xiaoyunque

    @property
    def has_jimeng(self) -> bool:
        return self.has_xiaoyunque

    @property
    def has_doubao_vlm(self) -> bool:
        return bool(self.volcengine_ark_key)

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_key) and not self.domestic_only

    @property
    def has_fal(self) -> bool:
        return bool(self.fal_key) and not self.domestic_only

    @property
    def has_video(self) -> bool:
        return self.has_xiaoyunque or bool(self.volcengine_ark_key) or bool(self.dashscope_key)

    @property
    def has_tts(self) -> bool:
        return bool(self.dashscope_key) or bool(self.volcengine_ark_key)

    @property
    def has_embedding(self) -> bool:
        return bool(self.dashscope_key)

    @property
    def has_tos(self) -> bool:
        return self.tos.configured

    def summary(self) -> dict[str, object]:
        """Capability map suitable for /health + smoke_keys reporting (masked)."""
        return {
            "domestic_only": self.domestic_only,
            "anthropic": {"enabled": self.has_anthropic, "key": _redact(self.anthropic_key)},
            "volcengine_visual": {
                "enabled": self.has_xiaoyunque,
                "ak": _redact(self.volcengine_visual_ak),
                "sk": _redact(self.volcengine_visual_sk),
                "region": self.volcengine_visual_region,
            },
            "volcengine_ark": {
                "enabled": self.has_doubao_vlm,
                "key": _redact(self.volcengine_ark_key),
            },
            "dashscope": {"enabled": bool(self.dashscope_key), "key": _redact(self.dashscope_key)},
            "elevenlabs": {"enabled": self.has_elevenlabs, "key": _redact(self.elevenlabs_key)},
            "fal": {"enabled": self.has_fal, "key": _redact(self.fal_key)},
            "tos": {
                "enabled": self.has_tos,
                "bucket": self.tos.bucket,
                "region": self.tos.region,
                "cdn": self.tos.cdn_domain or None,
            },
            "llm_chain": [
                {"name": e.name, "model": e.default_model, "kind": e.kind, "key": e.masked_key}
                for e in self.llm_endpoints
            ],
        }


def _domestic_only() -> bool:
    """全国产化开关（默认开启）。

    开启时仅装载境内厂商（火山方舟 / 通义 / DeepSeek / GLM / Kimi），并跳过
    境外厂商（Anthropic / Groq / Mistral / OpenAI 等）。设
    ``MANHUAJU_DOMESTIC_ONLY=false`` 可在境外信用卡环境下重新启用境外厂商。
    """
    return os.getenv("MANHUAJU_DOMESTIC_ONLY", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _build_llm_endpoints() -> tuple[ProviderEndpoint, ...]:
    """LLM endpoints in priority order — 国产优先（火山方舟 → 阿里 → DeepSeek → GLM → 月之暗面）。

    默认 ``llm_primary`` 为火山方舟 Doubao Seed 1.6（北京机房）。境外厂商
    （Anthropic/Groq/Mistral/OpenAI）仅在 ``MANHUAJU_DOMESTIC_ONLY=false`` 且配置了
    对应 API key 时才追加到队尾。
    """
    eps: list[ProviderEndpoint] = []
    domestic_only = _domestic_only()

    # ★ 国内首选：火山方舟 Doubao Seed 1.6（中文创作能力极强、价格低、走北京机房）
    if k := os.getenv("VOLCENGINE_API_KEY") or os.getenv("ARK_API_KEY") or os.getenv("VOLCENGINE_ARK_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="volcengine",
                api_key=k,
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                default_model="doubao-seed-1-6-250615",
                rpm=60,
            )
        )

    # 阿里通义千问 Qwen-Max / Qwen-Plus
    if k := os.getenv("DASHSCOPE_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="dashscope",
                api_key=k,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                default_model="qwen-plus",
                rpm=60,
            )
        )

    # DeepSeek V3.2 / R1
    if k := os.getenv("DEEPSEEK_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="deepseek",
                api_key=k,
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-chat",
                rpm=60,
            )
        )

    # 智谱 GLM-4.5
    if k := os.getenv("GLM_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="glm",
                api_key=k,
                base_url="https://open.bigmodel.cn/api/paas/v4",
                default_model="glm-4-flash",
                rpm=60,
            )
        )

    # 月之暗面 Kimi K2
    if k := os.getenv("MOONSHOT_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="moonshot",
                api_key=k,
                base_url="https://api.moonshot.cn/v1",
                default_model="moonshot-v1-32k",
                rpm=20,
            )
        )

    # ====== 境外厂商（仅 MANHUAJU_DOMESTIC_ONLY=false 时启用）======
    if not domestic_only:
        # 国际版（境外信用卡用户）：Claude Opus 4 — 编剧大脑顶配
        if k := os.getenv("ANTHROPIC_API_KEY"):
            eps.append(
                ProviderEndpoint(
                    name="anthropic",
                    api_key=k,
                    base_url="https://api.anthropic.com/v1",
                    default_model="claude-opus-4-20250514",
                    rpm=50,
                    kind="anthropic_native",
                    timeout_s=120.0,
                )
            )

        if k := os.getenv("GROQ_API_KEY"):
            eps.append(
                ProviderEndpoint(
                    name="groq",
                    api_key=k,
                    base_url="https://api.groq.com/openai/v1",
                    default_model="llama-3.3-70b-versatile",
                    rpm=30,
                )
            )

        if k := os.getenv("MISTRAL_API_KEY"):
            eps.append(
                ProviderEndpoint(
                    name="mistral",
                    api_key=k,
                    base_url="https://api.mistral.ai/v1",
                    default_model="mistral-large-latest",
                    rpm=30,
                )
            )

        if k := os.getenv("OPENAI_API_KEY"):
            eps.append(
                ProviderEndpoint(
                    name="openai",
                    api_key=k,
                    base_url="https://api.openai.com/v1",
                    default_model="gpt-4o-mini",
                    rpm=60,
                )
            )

    return tuple(eps)


def _build_tos() -> TOSSettings:
    return TOSSettings(
        ak=os.getenv("VOLCENGINE_TOS_AK", "").strip(),
        sk=os.getenv("VOLCENGINE_TOS_SK", "").strip(),
        region=os.getenv("VOLCENGINE_TOS_REGION", "cn-beijing").strip(),
        endpoint=os.getenv("VOLCENGINE_TOS_ENDPOINT", "tos-cn-beijing.volces.com").strip(),
        bucket=os.getenv("VOLCENGINE_TOS_BUCKET", "manhuaju-assets").strip(),
        cdn_domain=os.getenv("VOLCENGINE_TOS_CDN_DOMAIN", "").strip(),
    )


_settings_cache: ProviderSettings | None = None


def get_provider_settings(*, refresh: bool = False) -> ProviderSettings:
    """Singleton accessor. Pass refresh=True after re-loading .env in tests."""
    global _settings_cache  # noqa: PLW0603
    if _settings_cache is not None and not refresh:
        return _settings_cache

    if refresh:
        _load_env_once()

    s = ProviderSettings(
        llm_endpoints=_build_llm_endpoints(),
        volcengine_ark_key=(
            os.getenv("VOLCENGINE_ARK_API_KEY", "").strip()
            or os.getenv("VOLCENGINE_API_KEY", "").strip()
            or os.getenv("ARK_API_KEY", "").strip()
        ),
        volcengine_visual_ak=os.getenv("VOLCENGINE_VISUAL_AK", "").strip(),
        volcengine_visual_sk=os.getenv("VOLCENGINE_VISUAL_SK", "").strip(),
        volcengine_visual_region=os.getenv("VOLCENGINE_VISUAL_REGION", "cn-north-1").strip(),
        xiaoyunque_req_key=os.getenv(
            "VOLCENGINE_XIAOYUNQUE_REQ_KEY", "jimeng_t2v_v30"
        ).strip(),
        duanju_req_key=os.getenv(
            "VOLCENGINE_DUANJU_REQ_KEY",
            "jimeng_t2v_v30",
        ).strip(),
        seedream_req_key=os.getenv("VOLCENGINE_SEEDREAM_REQ_KEY", "seedream_5_0_t2i").strip(),
        jimeng_req_key=os.getenv("VOLCENGINE_JIMENG_REQ_KEY", "jimeng_high_aes_general_v46").strip(),
        dashscope_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        elevenlabs_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
        fal_key=os.getenv("FAL_KEY", "").strip(),
        gemini_key=os.getenv("GEMINI_API_KEY", "").strip(),
        xai_key=os.getenv("XAI_API_KEY", "").strip(),
        openai_key=os.getenv("OPENAI_API_KEY", "").strip(),
        tos=_build_tos(),
        postgres_dsn=os.getenv("POSTGRES_DSN", "").strip(),
        domestic_only=_domestic_only(),
    )
    _settings_cache = s
    return s


def env_path() -> Path:
    return project_root() / ".env"
