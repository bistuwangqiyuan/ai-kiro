"""T-0006 forbidden-terms scanner.

Scans `src/`, `config/`, and `scripts/` for any presence of human-in-the-loop
language. The scanner backs REQ-MO-008 / REQ-PILOT-011 (P-1 Autopilot Only).

Authoring AGENTS-only sources (`docs/`, `tests/`, `.kiro/`, this file itself,
and tasks.md self-declaration of the scanner) are ignored because they are
declaration zones.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_TERMS = [
    "human_required",
    "manual_review",
    "wait_for_approval",
    "operator_ack",
    "manual_approve",
    "wait_for_human",
    # Chinese variants - keep narrow to avoid false positives on legitimate words
    # in narrative content (e.g. novel text might contain 审核 in a different
    # context). Therefore we look for full-token compounds only.
    "操作员审核",
    "请运营审核",
    "需要人工确认",
    "需要人工审核",
    "需要人工介入",
]
FORBIDDEN_RE = re.compile("|".join(re.escape(t) for t in FORBIDDEN_TERMS))

INCLUDE_DIRS = ("src", "config", "scripts")
EXCLUDE_NAMES = {"forbidden_terms.py"}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".py", ".yaml", ".yml", ".toml", ".md", ".json"}:
                continue
            if p.name in EXCLUDE_NAMES:
                continue
            files.append(p)
    return files


def main() -> int:
    violations: list[tuple[Path, int, str]] = []
    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = FORBIDDEN_RE.search(line)
            if m:
                violations.append((p, i, line.strip()))

    if violations:
        print(f"[forbidden_terms] FAIL: {len(violations)} violation(s) found:", file=sys.stderr)
        for p, i, line in violations:
            print(f"  {p.relative_to(ROOT)}:{i}: {line}", file=sys.stderr)
        return 1
    print(f"[forbidden_terms] OK: scanned {len(iter_files())} files, 0 violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
