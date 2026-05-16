"""Live-mode provider configuration and `.env` ingestion.

Loads API keys from `.env` once and exposes them as immutable, masked-friendly
strings. All callers MUST go through `get_provider_settings()` rather than
reading os.environ directly so we have a single point of redaction in logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from manhuaju.utils.paths import project_root


def _load_env_once() -> None:
    """Idempotent .env load. Tolerant if file missing — Live adapters then NOOP."""
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

    @property
    def masked_key(self) -> str:
        return _redact(self.api_key)


@dataclass(frozen=True)
class ProviderSettings:
    """All provider keys + endpoints loaded from .env."""

    llm_endpoints: tuple[ProviderEndpoint, ...] = field(default_factory=tuple)
    volcengine_ark_key: str = ""
    dashscope_key: str = ""
    anthropic_key: str = ""
    gemini_key: str = ""
    xai_key: str = ""

    @property
    def has_any_llm(self) -> bool:
        return any(e.enabled and e.api_key for e in self.llm_endpoints)

    @property
    def has_video(self) -> bool:
        return bool(self.volcengine_ark_key) or bool(self.dashscope_key)

    @property
    def has_tts(self) -> bool:
        return bool(self.dashscope_key) or bool(self.volcengine_ark_key)

    @property
    def has_embedding(self) -> bool:
        return bool(self.dashscope_key)


def _build_llm_endpoints() -> tuple[ProviderEndpoint, ...]:
    """Endpoints in *priority order* — first one wins, on error → next.

    Priority chosen to put providers that have free / sufficient balance and
    high uptime first, so that pilot runs don't waste cycles on dead keys.
    Order can be overridden in `config/system.yaml :: live.llm.providers`.
    """
    eps: list[ProviderEndpoint] = []

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

    if k := os.getenv("VOLCENGINE_API_KEY"):
        eps.append(
            ProviderEndpoint(
                name="volcengine",
                api_key=k,
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                default_model="doubao-seed-1-6-250615",
                rpm=60,
            )
        )

    return tuple(eps)


_settings_cache: ProviderSettings | None = None


def get_provider_settings(*, refresh: bool = False) -> ProviderSettings:
    """Singleton accessor. Pass refresh=True after re-loading .env in tests."""
    global _settings_cache  # noqa: PLW0603 — explicit module-level cache
    if _settings_cache is not None and not refresh:
        return _settings_cache

    if refresh:
        _load_env_once()

    s = ProviderSettings(
        llm_endpoints=_build_llm_endpoints(),
        volcengine_ark_key=(
            os.getenv("VOLCENGINE_API_KEY", "").strip()
            or os.getenv("ARK_API_KEY", "").strip()
        ),
        dashscope_key=os.getenv("DASHSCOPE_API_KEY", ""),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gemini_key=os.getenv("GEMINI_API_KEY", ""),
        xai_key=os.getenv("XAI_API_KEY", ""),
    )
    _settings_cache = s
    return s


def env_path() -> Path:
    return project_root() / ".env"
