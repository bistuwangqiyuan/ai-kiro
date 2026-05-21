"""Supervised review gate (REQ-MODE-supervised).

Autopilot mode is a no-op. Supervised mode blocks release until approve/reject.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PARTIAL_RERENDER = "partial_rerender"


@dataclass
class ReviewGate:
    mode: str = "autopilot"
    _decisions: dict[str, ReviewDecision] = field(default_factory=dict)
    _notes: dict[str, str] = field(default_factory=dict)

    def episode_key(self, project_id: str, episode_id: str) -> str:
        return f"{project_id}:{episode_id}"

    def should_wait(self) -> bool:
        return self.mode == "supervised"

    def status(self, project_id: str, episode_id: str) -> ReviewDecision:
        return self._decisions.get(
            self.episode_key(project_id, episode_id), ReviewDecision.PENDING
        )

    def apply(
        self,
        project_id: str,
        episode_id: str,
        action: str,
        *,
        note: str = "",
    ) -> dict[str, Any]:
        key = self.episode_key(project_id, episode_id)
        action_l = action.lower().strip()
        if action_l in ("approve", "approved"):
            self._decisions[key] = ReviewDecision.APPROVED
        elif action_l in ("reject", "rejected"):
            self._decisions[key] = ReviewDecision.REJECTED
        elif action_l in ("partial_rerender", "partial", "rerender"):
            self._decisions[key] = ReviewDecision.PARTIAL_RERENDER
        else:
            raise ValueError(f"unknown review action: {action}")
        if note:
            self._notes[key] = note
        return {"episode_id": episode_id, "decision": self._decisions[key].value, "note": note}

    def is_release_allowed(self, project_id: str, episode_id: str) -> bool:
        if not self.should_wait():
            return True
        return self.status(project_id, episode_id) == ReviewDecision.APPROVED
