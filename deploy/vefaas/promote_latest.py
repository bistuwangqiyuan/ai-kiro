"""Force-publish the latest revision of a VeFaaS function.

The default ``provision.py`` flow calls ``release(revision_number=0)`` which
sometimes fails with HTTP 403 on our environment, leaving the new image as
"Latest" but never promoted to production traffic. This helper:

1. Lists revisions for a function id.
2. Picks the highest-numbered one (or one matching ``--image-tag``).
3. Calls ``release`` with that explicit revision number and 100% traffic.
4. Polls ``get_release_status`` until it reaches ``done``/``failed``.

Usage:

    python deploy/vefaas/promote_latest.py --function-id ex9xkzt4
    python deploy/vefaas/promote_latest.py --function-id ex9xkzt4 --image-tag 9a8c50d3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy" / "vefaas"))


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--function-id", default="ex9xkzt4")
    p.add_argument("--region", default="cn-beijing")
    p.add_argument("--image-tag", default=None, help="if given, pick revision whose source ends with :<tag>")
    p.add_argument("--latest", action="store_true", help="force pick the highest revision number")
    p.add_argument("--timeout-s", type=int, default=300)
    args = p.parse_args(argv)

    env = _load_env(ROOT / ".env")
    ak = env.get("VOLCENGINE_VISUAL_AK") or os.environ.get("VOLCENGINE_VISUAL_AK")
    sk = env.get("VOLCENGINE_VISUAL_SK") or os.environ.get("VOLCENGINE_VISUAL_SK")
    if not ak or not sk:
        print("ERR: missing VOLCENGINE_VISUAL_AK/SK", file=sys.stderr)
        return 2

    import volcenginesdkcore as core
    import volcenginesdkvefaas as vefaas

    cfg = core.Configuration()
    cfg.ak = ak
    cfg.sk = sk
    cfg.region = args.region
    core.Configuration.set_default(cfg)

    api = vefaas.VEFAASApi()
    fid = args.function_id

    # 1) Look up the existing function to find the current Latest source.
    info = api.get_function(vefaas.GetFunctionRequest(id=fid))
    print(f"[promote] function name={getattr(info,'name',None)} source={getattr(info,'source',None)}")

    # 2) List revisions, pick the right one.
    revs = api.list_revisions(
        vefaas.ListRevisionsRequest(function_id=fid, page_number=1, page_size=50)
    )
    items = list(getattr(revs, "items", []) or [])
    if not items:
        print("[promote] no revisions found", file=sys.stderr)
        return 1
    items.sort(key=lambda r: int(getattr(r, "revision_number", 0) or 0), reverse=True)
    print("[promote] revisions:")
    for r in items[:8]:
        rn = getattr(r, "revision_number", None)
        src = getattr(r, "source", "") or ""
        print(f"  rev={rn} source={src[-80:]}")

    target = None
    if args.image_tag:
        for r in items:
            if (getattr(r, "source", "") or "").endswith(":" + args.image_tag):
                target = r
                break
    if target is None:
        target = items[0]
    rn = int(getattr(target, "revision_number", 0) or 0)
    src = getattr(target, "source", "")
    print(f"[promote] picked revision={rn} source={src}")

    # 3) Release that revision at 100% traffic.
    req = vefaas.ReleaseRequest(
        function_id=fid,
        revision_number=rn,
        target_traffic_weight=100,
        description=f"manual promote rev={rn}",
    )
    try:
        api.release(req)
        print(f"[promote] release submitted rev={rn}")
    except Exception as e:  # noqa: BLE001
        print(f"[promote] release call failed: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        return 3

    # 4) Poll release status.
    deadline = time.time() + args.timeout_s
    last = ""
    while time.time() < deadline:
        try:
            rs = api.get_release_status(vefaas.GetReleaseStatusRequest(function_id=fid))
            status = getattr(rs, "status", None)
            stable = getattr(rs, "stable_revision_number", None)
            new = (
                getattr(rs, "new_revision_number", None)
                or getattr(rs, "current_revision_number", None)
            )
            line = f"status={status} stable={stable} new={new}"
            if line != last:
                print(f"[promote] {line}")
                last = line
            if status in ("done", "succeed", "succeeded"):
                if stable == rn:
                    print(f"[promote] OK — stable now rev={rn}")
                    return 0
                # Some SDKs report 'done' even after polling, but the stable
                # has not yet caught up; keep polling briefly.
            if status == "failed":
                print(
                    "[promote] release FAILED: "
                    f"code={getattr(rs,'error_code',None)} msg={getattr(rs,'status_message',None)}",
                    file=sys.stderr,
                )
                return 4
        except Exception as e:  # noqa: BLE001
            print(f"[promote] poll error: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        time.sleep(5)

    print("[promote] timed out waiting for release to complete", file=sys.stderr)
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
