"""Template engine for one-click viral genre packs (REQ-TPL-001..006).

Loads ``config/templates/<id>.yaml`` and renders a ready-to-run project
configuration by merging:

1. ``defaults`` (locked tier / threshold values) from the template.
2. The user's variable overrides.
3. The variable substitution pass over ``shot_plan_template`` (a tiny safe
   ``{{ var }}`` substituter — *not* full Jinja2, to avoid runtime injection).

The output is a ``RenderedTemplate`` ready to feed into ``mode_router``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manhuaju.utils.paths import config_dir

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class TemplateVariable:
    name: str
    type: str
    required: bool
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class RenderedTemplate:
    template_id: str
    defaults: dict[str, Any]
    variables: dict[str, Any]
    shot_plans_per_episode: tuple[tuple[dict[str, Any], ...], ...]
    distribution: dict[str, Any]


def _substitute(value: Any, vars_: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in vars_:
                return match.group(0)  # leave un-substituted vars in place
            return str(vars_[key])

        return _VAR_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_substitute(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, vars_) for k, v in value.items()}
    return value


@dataclass
class TemplateEngine:
    templates_dir: Path = field(default_factory=lambda: config_dir() / "templates")

    def list_templates(self) -> list[str]:
        if not self.templates_dir.exists():
            return []
        return sorted(p.stem for p in self.templates_dir.glob("*.yaml"))

    def load(self, template_id: str) -> dict[str, Any]:
        path = self.templates_dir / f"{template_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"unknown template: {template_id!r}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def get_variables(self, template_id: str) -> list[TemplateVariable]:
        spec = self.load(template_id)
        return [
            TemplateVariable(
                name=str(v["name"]),
                type=str(v.get("type", "string")),
                required=bool(v.get("required", False)),
                default=v.get("default"),
                description=str(v.get("description", "")),
            )
            for v in spec.get("variables", [])
        ]

    def render(
        self,
        template_id: str,
        user_variables: dict[str, Any],
        episode_count: int | None = None,
    ) -> RenderedTemplate:
        """Substitute user vars and emit a ready-to-execute config.

        Required variables that are missing raise ``ValueError``.
        """

        spec = self.load(template_id)
        defaults = dict(spec.get("defaults", {}))
        ep_count = episode_count or int(defaults.get("episode_count", 3))
        defaults["episode_count"] = ep_count

        var_specs = self.get_variables(template_id)
        merged_vars: dict[str, Any] = {}
        missing: list[str] = []
        for v in var_specs:
            if v.name in user_variables and user_variables[v.name] not in (None, ""):
                merged_vars[v.name] = user_variables[v.name]
            elif v.default is not None:
                merged_vars[v.name] = v.default
            elif v.required:
                missing.append(v.name)
            else:
                merged_vars[v.name] = ""
        if missing:
            raise ValueError(f"missing required template variables: {missing}")

        shot_plans = []
        raw_shots = spec.get("shot_plan_template", [])
        for ep in range(1, ep_count + 1):
            ep_vars = dict(merged_vars)
            ep_vars["ep"] = ep
            substituted = tuple(_substitute(s, ep_vars) for s in raw_shots)
            shot_plans.append(substituted)

        distribution = _substitute(spec.get("distribution", {}), merged_vars)
        return RenderedTemplate(
            template_id=template_id,
            defaults=defaults,
            variables=merged_vars,
            shot_plans_per_episode=tuple(shot_plans),
            distribution=distribution,
        )
