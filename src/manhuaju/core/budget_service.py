"""Budget service — REQ-IN-010 / REQ-MO-005 / REQ-NFR-COST-001..003."""

from __future__ import annotations

from manhuaju.schemas import Budget

# Tier table per design §13.1
TIER_TABLE = {
    "S": {"max_tokens": 5_000_000, "max_seconds": 4 * 3600, "max_credits": 6_000},
    "M": {"max_tokens": 12_000_000, "max_seconds": 8 * 3600, "max_credits": 12_000},
    "L": {"max_tokens": 24_000_000, "max_seconds": 12 * 3600, "max_credits": 24_000},
    "XL": {"max_tokens": 48_000_000, "max_seconds": 24 * 3600, "max_credits": 48_000},
}


def make_budget(tier: str) -> Budget:
    t = TIER_TABLE.get(tier, TIER_TABLE["S"])
    reserve = max(1, int(t["max_credits"] * 0.05))
    return Budget(
        max_tokens=t["max_tokens"],
        max_seconds=t["max_seconds"],
        max_credits=t["max_credits"],
        reserved_credits=reserve,
    )


class BudgetService:
    def __init__(self, budget: Budget) -> None:
        self.budget = budget

    def check(self, *, credits: int = 0, tokens: int = 0, seconds: int = 0) -> bool:
        """Return True if there is enough remaining budget on every axis."""
        if credits > self.budget.remaining_credits():
            return False
        if tokens and self.budget.used_tokens + tokens > self.budget.max_tokens:
            return False
        if seconds and self.budget.used_seconds + seconds > self.budget.max_seconds:
            return False
        return True

    def charge(self, *, credits: int = 0, tokens: int = 0, seconds: int = 0) -> None:
        self.budget.charge(credits=credits, tokens=tokens, seconds=seconds)

    def utilisation(self) -> float:
        if self.budget.max_credits == 0:
            return 0.0
        return self.budget.used_credits / self.budget.max_credits

    def should_downgrade(self) -> bool:
        return self.utilisation() > 0.95
