"""Unified `manhuaju` CLI for the v4 fast-path.

Sub-commands:

    manhuaju keys                     # smoke test all v4 provider keys
    manhuaju keys --strict --json     # CI-friendly
    manhuaju pilot --novel X --out Y  # mock 3-ep pilot
    manhuaju live --suite three       # live 3-ep pilot
    manhuaju serve --port 8080        # FastAPI dev server
    manhuaju version                  # print package version
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

PKG_VERSION = "0.4.0"


def cmd_keys(args: argparse.Namespace) -> int:
    mod = importlib.import_module("scripts.smoke_keys")
    sys.argv = ["smoke_keys"] + (["--strict"] if args.strict else []) + (["--json"] if args.json else [])
    return mod.main()


def cmd_pilot(args: argparse.Namespace) -> int:
    mod = importlib.import_module("scripts.run_pilot")
    return mod.cli(
        novel=Path(args.novel) if args.novel else None,
        config=Path(args.config) if args.config else None,
        out=Path(args.out) if args.out else None,
        reports=Path(args.reports) if args.reports else None,
    )


def cmd_live(args: argparse.Namespace) -> int:
    import os

    mod = importlib.import_module("scripts.run_live_pilot")
    if args.suite:
        os.environ["MANHUAJU_LIVE_SUITE"] = args.suite
    if args.mode:
        os.environ["MANHUAJU_LIVE_MODE"] = args.mode
    if args.resume:
        os.environ["MANHUAJU_LIVE_RESUME"] = "1"
    return mod.cli() if hasattr(mod, "cli") else mod.main()


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "manhuaju.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"manhuaju-autopilot {PKG_VERSION}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manhuaju", description="AI 漫剧 Autopilot v4 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_keys = sub.add_parser("keys", help="smoke-test all provider keys")
    p_keys.add_argument("--strict", action="store_true")
    p_keys.add_argument("--json", action="store_true")
    p_keys.set_defaults(func=cmd_keys)

    p_pilot = sub.add_parser("pilot", help="run a mock 3-episode pilot")
    p_pilot.add_argument("--novel", required=False)
    p_pilot.add_argument("--config", required=False)
    p_pilot.add_argument("--out", required=False)
    p_pilot.add_argument("--reports", required=False)
    p_pilot.set_defaults(func=cmd_pilot)

    p_live = sub.add_parser("live", help="run a live pilot")
    p_live.add_argument("--suite", choices=["one", "three"], default="one")
    p_live.add_argument("--mode", choices=["live", "hybrid", "mock"], default=None)
    p_live.add_argument("--resume", action="store_true")
    p_live.set_defaults(func=cmd_live)

    p_serve = sub.add_parser("serve", help="run FastAPI dev server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.add_argument("--workers", type=int, default=1)
    p_serve.set_defaults(func=cmd_serve)

    p_ver = sub.add_parser("version", help="print version")
    p_ver.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
