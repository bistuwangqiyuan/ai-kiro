"""Auto-cut: align scene transitions to BGM beats (REQ-AC-002..006).

Given a list of ``ShotPlan`` objects (each with desired ``in_s`` / ``out_s``
timestamps) and a ``BeatTrack``, produce a list of adjusted shot timings
that snap transition boundaries to the nearest beat. The adjustment must:

* Preserve total episode duration within ±0.5s (REQ-AC-003).
* Never let any individual shot grow > 25% or shrink < 50% of its original
  length (REQ-AC-004).
* Mark unaligned shots as ``aligned=False`` so the renderer can decide
  whether to keep the original cut.
"""

from __future__ import annotations

from dataclasses import dataclass

from manhuaju.services.music_alignment import BeatTrack, snap_to_beats

#: REQ-AC-003: max allowed total duration drift after snapping.
MAX_TOTAL_DRIFT_S = 0.5
#: REQ-AC-004: per-shot bounds.
MAX_SHOT_GROWTH_RATIO = 1.25
MIN_SHOT_SHRINK_RATIO = 0.50
#: REQ-AC-002: snap-window for individual transitions.
DEFAULT_SNAP_DRIFT_S = 0.20


@dataclass
class ShotPlan:
    shot_id: str
    in_s: float
    out_s: float

    @property
    def duration(self) -> float:
        return max(0.0, self.out_s - self.in_s)


@dataclass
class AlignedShot:
    shot_id: str
    in_s: float
    out_s: float
    original_duration: float
    aligned: bool
    drift_s: float

    @property
    def duration(self) -> float:
        return max(0.0, self.out_s - self.in_s)


def align(
    shots: list[ShotPlan],
    beats: BeatTrack,
    *,
    snap_drift_s: float = DEFAULT_SNAP_DRIFT_S,
) -> list[AlignedShot]:
    """REQ-AC-002 + -004: snap transitions to beats while honouring per-shot bounds.

    The function snaps each ``out_s`` (= next ``in_s``) to the nearest beat
    inside ``snap_drift_s``; shots whose adjusted duration violates the
    growth/shrink bounds revert to their original timing.
    """

    if not shots:
        return []

    transitions = [s.out_s for s in shots[:-1]]  # last shot's out_s is end-of-episode
    snapped = snap_to_beats(transitions, beats.beats_s, max_drift=snap_drift_s)

    out: list[AlignedShot] = []
    prev_in = shots[0].in_s
    for i, shot in enumerate(shots):
        if i < len(shots) - 1:
            new_out = snapped[i]
        else:
            new_out = shot.out_s

        new_duration = new_out - prev_in
        original_duration = shot.duration
        # REQ-AC-004: enforce per-shot growth/shrink bounds.
        within_bounds = (
            new_duration >= MIN_SHOT_SHRINK_RATIO * original_duration
            and new_duration <= MAX_SHOT_GROWTH_RATIO * original_duration
        )
        if within_bounds and new_duration > 0:
            aligned_in = prev_in
            aligned_out = new_out
            aligned = aligned_out != shot.out_s
            drift = aligned_out - shot.out_s
        else:
            aligned_in = shot.in_s
            aligned_out = shot.out_s
            aligned = False
            drift = 0.0
        out.append(
            AlignedShot(
                shot_id=shot.shot_id,
                in_s=round(aligned_in, 4),
                out_s=round(aligned_out, 4),
                original_duration=round(original_duration, 4),
                aligned=aligned,
                drift_s=round(drift, 4),
            )
        )
        prev_in = aligned_out
    return out


def total_duration_drift(originals: list[ShotPlan], aligned: list[AlignedShot]) -> float:
    """REQ-AC-003: aggregate drift between original and aligned timelines."""

    if not originals or not aligned:
        return 0.0
    orig_total = originals[-1].out_s - originals[0].in_s
    aligned_total = aligned[-1].out_s - aligned[0].in_s
    return aligned_total - orig_total
