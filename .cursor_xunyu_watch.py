"""Resilient watcher for an in-flight xunyu project: poll -> verify -> promote."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com"
PID = sys.argv[1] if len(sys.argv) > 1 else "proj_48075cfbbec5"
JID = sys.argv[2] if len(sys.argv) > 2 else "2d775c53-9664-4386-8430-ecf64b49fac1"
TITLE = "荀彧劝曹操迎献帝 · 15s 720p真人测试"
DEADLINE_MIN = 40


def g(path: str, timeout: float = 60.0):
    for i in range(6):
        try:
            return httpx.get(BASE + path, timeout=timeout, verify=False)
        except httpx.HTTPError:
            time.sleep(min(4 + i * 2, 15))
    return None


def main() -> int:
    deadline = time.time() + DEADLINE_MIN * 60
    last = None
    proj: dict = {}
    while time.time() < deadline:
        rp = g(f"/v1/projects/{PID}")
        if rp is not None and rp.status_code == 200:
            proj = rp.json()
        rj = g(f"/v1/batch/jobs/{JID}")
        bst = rj.json().get("status") if (rj is not None and rj.status_code == 200) else "n/a"
        cur = (proj.get("status"), proj.get("stage"), bst)
        if cur != last:
            print(f"[poll] proj={cur[0]}/{cur[1]} batch={cur[2]}", flush=True)
            last = cur
        if proj.get("status") in ("released", "succeeded", "completed", "failed"):
            break
        if bst == "failed":
            print("[poll] batch failed", flush=True)
            rj2 = g(f"/v1/batch/jobs/{JID}")
            if rj2 is not None:
                print(rj2.text[:400], flush=True)
            break
        time.sleep(25)

    print(f"[done] status={proj.get('status')}", flush=True)
    # Find gallery entry for the project.
    gl = g(f"/v1/gallery?project_id={PID}")
    vids = gl.json().get("videos", []) if (gl is not None and gl.status_code == 200) else []
    print(f"[gallery] entries={len(vids)}", flush=True)
    if not vids:
        print("[fail] no gallery entry", flush=True)
        return 2
    v = vids[0]
    vid = v["video_id"]
    is_sample = v.get("is_sample")
    print(f"[gallery] vid={vid} is_sample={is_sample}", flush=True)

    # Download and inspect.
    dl = ROOT / "api_data" / "_dl" / f"{vid}.mp4"
    dl.parent.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        try:
            r = httpx.get(f"{BASE}/media/videos/{vid}", timeout=300, verify=False)
            if r.status_code == 200:
                dl.write_bytes(r.content)
                break
        except httpx.HTTPError:
            time.sleep(5)
    size = dl.stat().st_size if dl.is_file() else 0
    print(f"[download] {size} bytes", flush=True)
    rr = subprocess.run(["ffmpeg", "-i", str(dl), "-hide_banner"], capture_output=True, text=True)
    for line in rr.stderr.splitlines():
        if "Duration" in line or "Stream #" in line:
            print("  " + line.strip(), flush=True)

    if size < 200_000:
        print("[fail] video too small / not real", flush=True)
        return 3

    # Promote to local web/samples so it ships to all users on next deploy.
    from manhuaju.services.video_gallery import VideoGallery, promote_real_video_to_samples
    from manhuaju.utils.paths import project_root

    gal = VideoGallery(ROOT / "api_data" / "gallery.sqlite")
    entry = promote_real_video_to_samples(
        gallery=gal,
        web_dir=project_root() / "web",
        mp4_path=dl,
        project_id=PID,
        episode_id="ep01",
        title=TITLE,
        genre="ancient",
    )
    if entry:
        print(f"[promote] sample {entry.video_id} -> {entry.local_video}", flush=True)
        print("[ok] promoted", flush=True)
        return 0
    print("[promote] skipped (too small)", flush=True)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
