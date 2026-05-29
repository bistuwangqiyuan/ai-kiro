#!/usr/bin/env python3
"""Submit 荀彧迎献帝 30s 720p photoreal pilot; poll; promote to sample gallery on success."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

XUNYU_NOVEL = """
建安元年，许都空悬，汉室名存实亡。深夜，谋士荀彧入丞相府，向曹操陈说迎天子之策。
荀彧拱手道：「诏敕虽微，然名号天下共认。将军若迎天子而奉之，则名正言顺，诸侯莫敢先动。」
曹操抚须沉思，烛火映甲，殿外风声猎猎。荀彧又言：「此乃万世之基，不可失时。」
曹操缓缓起身，目光如炬：「便依文若之计。」
""".strip()

DEFAULT_BASE = os.environ.get(
    "MANHUAJU_API_BASE",
    "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--timeout-min", type=int, default=35)
    ap.add_argument("--poll-s", type=int, default=25)
    ap.add_argument("--promote", action="store_true", default=True)
    ap.add_argument("--no-promote", action="store_false", dest="promote")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    payload = {
        "mode": "pro",
        "title": "荀彧劝曹操迎献帝 · 720p真人测试",
        "novel_text": XUNYU_NOVEL,
        "language": "zh",
        "episode_count": 1,
        "episode_duration_s": 30,
        "style_preset_id": "photoreal_historical_v1",
        "genre": "ancient",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "visual_style": "真人写实, 电影质感, 三国历史, 烛光暖色, 汉服甲胄细节",
    }
    print(f"[submit] POST {base}/v1/projects", flush=True)
    r = httpx.post(f"{base}/v1/projects", json=payload, timeout=120, verify=False)
    print(f"[submit] HTTP {r.status_code}", flush=True)
    if r.status_code != 200:
        print(r.text[:800])
        return 1
    body = r.json()
    pid = body["project_id"]
    jid = body.get("job_id") or ""
    print(f"  project_id={pid} executor={body.get('executor')} job_id={jid}", flush=True)

    deadline = time.time() + args.timeout_min * 60
    last = None
    while time.time() < deadline:
        rp = httpx.get(f"{base}/v1/projects/{pid}", timeout=60, verify=False)
        proj = rp.json() if rp.status_code == 200 else {}
        state = (proj.get("status"), proj.get("stage"))
        batch_st = ""
        if jid:
            rj = httpx.get(f"{base}/v1/batch/jobs/{jid}", timeout=60, verify=False)
            if rj.status_code == 200:
                batch_st = rj.json().get("status", "")
        if state != last:
            print(f"[poll] proj={state[0]}/{state[1]} batch={batch_st or 'n/a'}", flush=True)
            last = state
        if proj.get("status") in ("released", "succeeded", "completed", "failed"):
            break
        time.sleep(args.poll_s)

    if proj.get("status") not in ("released", "succeeded", "completed"):
        print("[fail] project did not complete in time", flush=True)
        return 2

    manifest = proj.get("manifest") or {}
    gallery = proj.get("gallery_videos") or []
    print(f"[done] status={proj.get('status')} gallery_entries={len(gallery)}", flush=True)

    mp4_path: Path | None = None
    for ep in manifest.get("episodes") or []:
        p = ep.get("final_mp4")
        if p and Path(p).is_file():
            mp4_path = Path(p)
            break
    if mp4_path is None and gallery:
        lv = gallery[0].get("local_video") or gallery[0].get("local_path")
        if lv and Path(lv).is_file():
            mp4_path = Path(lv)

    is_sample = None
    if gallery:
        is_sample = gallery[0].get("is_sample")
    print(f"[gallery] is_sample={is_sample} mp4={mp4_path}", flush=True)

    if is_sample:
        print("[warn] gallery still marked sample — may not be a real render", flush=True)
        return 3

    if args.promote:
        from manhuaju.services.video_gallery import VideoGallery, promote_real_video_to_samples
        from manhuaju.utils.paths import project_root

        web_dir = project_root() / "web"
        gal = VideoGallery(ROOT / "api_data" / "gallery.sqlite")

        if not mp4_path or not mp4_path.is_file():
            gl = httpx.get(f"{base}/v1/gallery", params={"project_id": pid}, timeout=60, verify=False)
            if gl.status_code == 200:
                for v in gl.json().get("videos") or []:
                    vid = v.get("video_id")
                    if not vid:
                        continue
                    tmp = ROOT / "api_data" / "_dl" / f"{vid}.mp4"
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    with httpx.stream(
                        "GET", f"{base}/media/videos/{vid}", timeout=300, verify=False
                    ) as resp:
                        if resp.status_code == 200:
                            tmp.write_bytes(resp.read())
                            if tmp.stat().st_size > 200_000:
                                mp4_path = tmp
                                print(f"[download] {tmp.stat().st_size} bytes from /media/videos/{vid}", flush=True)
                            break

        if mp4_path and mp4_path.is_file():
            entry = promote_real_video_to_samples(
                gallery=gal,
                web_dir=web_dir,
                mp4_path=mp4_path,
                project_id=pid,
                episode_id="ep01",
                title=payload["title"],
                genre="ancient",
            )
            if entry:
                print(f"[promote] added sample {entry.video_id} -> {entry.local_video}", flush=True)
            else:
                print("[promote] skipped (file too small)", flush=True)
        else:
            print("[promote] no mp4 to copy into web/samples", flush=True)

    print(f"[ok] watch at {base}/gallery.html", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
