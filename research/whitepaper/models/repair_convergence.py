"""Repair-loop absorbing Markov chain.

States: ``fail``, ``repairing``, ``pass``, ``hard_fail`` (after N retries).
Transition skeleton (per attempt):

    fail        --(1)-->        repairing
    repairing   --(p_pass)-->   pass
    repairing   --(1-p_pass)--> repairing  (until N attempts)
    after N attempts            hard_fail

Outputs:
- E[iterations until pass]
- P(hard_fail)
- retry_factor (extra cost multiplier)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RepairResult:
    p_pass_per_attempt: float
    max_attempts: int
    expected_attempts: float
    p_hard_fail: float
    retry_factor: float

    def as_dict(self) -> dict[str, float]:
        return {
            "p_pass_per_attempt": round(self.p_pass_per_attempt, 4),
            "max_attempts": self.max_attempts,
            "expected_attempts": round(self.expected_attempts, 4),
            "p_hard_fail": round(self.p_hard_fail, 6),
            "retry_factor": round(self.retry_factor, 4),
        }


def _expected_attempts_truncated(p: float, n: int) -> float:
    """E[number of trials until first success | success within n trials], capped at n."""

    if p <= 0:
        return float(n)
    # E[N] for geometric truncated at n =
    # sum_{k=1..n} k*p*(1-p)^(k-1) + n*(1-p)^n   (assigns n if no success)
    return float(sum(k * p * (1 - p) ** (k - 1) for k in range(1, n + 1)) + n * (1 - p) ** n)


def evaluate(p_pass_per_attempt: float = 0.65, max_attempts: int = 4) -> RepairResult:
    p_hard_fail = (1 - p_pass_per_attempt) ** max_attempts
    e_attempts = _expected_attempts_truncated(p_pass_per_attempt, max_attempts)
    # retry_factor = (E[attempts] - 1) since first attempt is the original cost
    retry_factor = max(e_attempts - 1.0, 0.0)
    return RepairResult(
        p_pass_per_attempt=p_pass_per_attempt,
        max_attempts=max_attempts,
        expected_attempts=e_attempts,
        p_hard_fail=p_hard_fail,
        retry_factor=retry_factor,
    )


def summary(rng: np.random.Generator | None = None) -> dict[str, object]:  # rng unused; pure analytical
    out: dict[str, object] = {}
    for p in (0.50, 0.65, 0.75, 0.85, 0.92):
        for n in (2, 3, 4, 5):
            out[f"p_{p}_n_{n}"] = evaluate(p, n).as_dict()
    out["recommended_default"] = evaluate(0.75, 4).as_dict()
    out["repair_factor_for_cost_model"] = round(out["recommended_default"]["retry_factor"], 4)  # type: ignore[index]
    return out
