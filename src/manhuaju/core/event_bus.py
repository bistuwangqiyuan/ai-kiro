"""In-memory event bus (M2 replacement for NATS JetStream).

Persists every event to a `state_journal.jsonl` so re-play is bit-exact
(REQ-MO-002 / REQ-MO-003).
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from manhuaju.schemas import Event, now


class InMemoryEventBus:
    def __init__(self, journal_path: Path | None = None) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._wildcards: list[Callable[[Event], None]] = []
        self._events: list[Event] = []
        self._journal_path = journal_path
        if journal_path is not None:
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text("", encoding="utf-8")  # truncate

    def subscribe(self, subject: str, handler: Callable[[Event], None]) -> None:
        if subject == "*":
            self._wildcards.append(handler)
        else:
            self._subs[subject].append(handler)

    def publish(
        self,
        subject: str,
        *,
        project_id: str,
        episode_id: str | None = None,
        shot_id: str | None = None,
        payload: dict[str, Any] | None = None,
        trace_id: str = "",
    ) -> Event:
        ev = Event(
            event_id=str(uuid.uuid4()),
            subject=subject,
            project_id=project_id,
            episode_id=episode_id,
            shot_id=shot_id,
            trace_id=trace_id,
            ts=now(),
            payload=dict(payload or {}),
        )
        self._events.append(ev)
        if self._journal_path is not None:
            with self._journal_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        ev.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
                    )
                    + "\n"
                )
        for h in self._subs.get(subject, []):
            h(ev)
        for h in self._wildcards:
            h(ev)
        return ev

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def filter(self, subject_prefix: str) -> list[Event]:
        return [e for e in self._events if e.subject.startswith(subject_prefix)]
