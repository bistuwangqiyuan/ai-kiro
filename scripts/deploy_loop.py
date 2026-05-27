"""Deploy + verify loop driver.

Runs ``scripts/user_portal_gate.py`` against the live base URL in a loop. When
any gate FAILs, prints the failure list, picks up the latest already-built
image tag (short HEAD SHA, 8 chars by default), pushes it to VeFaaS via
``deploy/vefaas/provision.py --step functions --image-tag <sha>``, sleeps a
moment for the cold start, and reruns the gate. The loop keeps going until all
gates report PASS (no iteration cap, per plan choice) or the operator stops it
with Ctrl-C.

Code fixes between iterations are still made manually from Cursor; this script
handles the "kick deployment + re-verify" half so the human-in-the-loop part is
just edits + ``git push``.

Usage:

    python scripts/deploy_loop.py \
        --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com

Optional flags:

    --image-tag <sha>     Force a specific tag instead of git HEAD.
    --skip-redeploy       Don't run provision.py between iterations (gate-only).
    --max-iterations N    Hard cap (default 0 = unlimited).
    --gate-args '...'     Extra args forwarded to user_portal_gate.py.
    --interval-s 30       Sleep seconds between iterations.
    --max-iter-seconds N  Hard wallclock cap on the whole loop (default 0 = unlimited).
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "scripts" / "user_portal_gate.py"
PROVISION_SCRIPT = REPO_ROOT / "deploy" / "vefaas" / "provision.py"

DEFAULT_BASE = "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com"

PASS_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)\s+—\s*(.*)$")


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _git_short_sha(length: int = 8) -> str | None:
    code, out = _run(["git", "rev-parse", "HEAD"])
    if code != 0:
        return None
    sha = out.strip()
    return sha[:length] if sha else None


def run_gate(base: str, extra: list[str]) -> tuple[bool, list[tuple[bool, str, str]], str]:
    cmd = [sys.executable, str(GATE_SCRIPT), "--base", base, *extra]
    code, out = _run(cmd)
    rows: list[tuple[bool, str, str]] = []
    for line in out.splitlines():
        m = PASS_RE.match(line.strip())
        if not m:
            continue
        rows.append((m.group(1) == "PASS", m.group(2), m.group(3)))
    all_pass = bool(rows) and all(r[0] for r in rows) and code == 0
    return all_pass, rows, out


def redeploy(image_tag: str) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(PROVISION_SCRIPT),
        "--step",
        "functions",
        "--image-tag",
        image_tag,
    ]
    code, out = _run(cmd)
    return code == 0, out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deploy + verify loop driver")
    p.add_argument("--base", default=DEFAULT_BASE, help="public base URL of the deployed API")
    p.add_argument("--image-tag", default=None, help="override image tag (default = git HEAD short SHA)")
    p.add_argument("--skip-redeploy", action="store_true", help="don't call provision.py between iterations")
    p.add_argument("--max-iterations", type=int, default=0, help="hard cap on iterations (0 = unlimited)")
    p.add_argument("--max-iter-seconds", type=int, default=0, help="hard wallclock cap (0 = unlimited)")
    p.add_argument("--interval-s", type=float, default=30.0, help="sleep between iterations")
    p.add_argument("--gate-args", default="", help="extra args forwarded to user_portal_gate.py (string)")
    args = p.parse_args(argv)

    extra = shlex.split(args.gate_args) if args.gate_args else []
    started = time.time()
    iteration = 0

    print(f"[loop] base={args.base}")
    print(f"[loop] gate={GATE_SCRIPT.relative_to(REPO_ROOT)}")
    if args.skip_redeploy:
        print("[loop] redeploy disabled (gate-only)")
    else:
        print(f"[loop] provision={PROVISION_SCRIPT.relative_to(REPO_ROOT)}")
    print(
        f"[loop] interval={args.interval_s}s, "
        f"max-iters={args.max_iterations or '∞'}, "
        f"max-wallclock={args.max_iter_seconds or '∞'}s"
    )

    while True:
        iteration += 1
        print(f"\n========== iteration {iteration} ==========")
        all_pass, rows, output = run_gate(args.base, extra)
        if not rows:
            print("[loop] gate produced no PASS/FAIL rows — printing raw output:")
            print(output)
        else:
            for ok, name, note in rows:
                mark = "PASS" if ok else "FAIL"
                print(f"  [{mark}] {name:<22} {note}")
        if all_pass:
            elapsed = time.time() - started
            print(f"\n[loop] ALL GREEN after {iteration} iteration(s) in {elapsed:.1f}s")
            return 0

        # Check caps before redeploying / sleeping.
        if args.max_iterations and iteration >= args.max_iterations:
            print(f"[loop] max-iterations ({args.max_iterations}) reached — stopping")
            return 1
        if args.max_iter_seconds and (time.time() - started) > args.max_iter_seconds:
            print(f"[loop] max-iter-seconds ({args.max_iter_seconds}) exceeded — stopping")
            return 1

        if not args.skip_redeploy:
            tag = args.image_tag or _git_short_sha()
            if not tag:
                print("[loop] could not resolve image tag (git HEAD missing?), skipping redeploy")
            else:
                print(f"[loop] redeploying image tag={tag} via provision.py …")
                ok, plog = redeploy(tag)
                print(plog)
                if not ok:
                    print(f"[loop] provision.py FAILED — will retry next iteration")

        print(f"[loop] sleeping {args.interval_s}s before next iteration …")
        try:
            time.sleep(args.interval_s)
        except KeyboardInterrupt:
            print("\n[loop] interrupted by operator")
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
