"""跨集人脸一致性服务 — 防线 4 ArcFace 嵌入矩阵.

策略（按可用性级联）：
1. 优先：``insightface`` (buffalo_l) — CPU 推理 ~300ms/帧，ArcFace 嵌入余弦。
2. 兜底：纯哈希代理（M2/M3 已有形态），永远可用但不可比真值。

接口：
- ``compute_episode_embedding(video_path, char_id) -> np.ndarray``
- ``cross_episode_matrix(embeddings_per_episode) -> dict[char_id, dict[(ep_a, ep_b), float]]``
- ``arcface_min(matrix) -> float`` —— 主角跨集最小相似度（v4 KPI 0.92）

docx 十二节「质量评估与自我修正 - 自动评估」第 6 条：无崩坏（面/手/肢）。
"""

from __future__ import annotations

import contextlib
import hashlib
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import numpy as np  # type: ignore[import-not-found]

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False


@dataclass
class FaceEmbedding:
    char_id: str
    episode_id: str
    frame_idx: int
    vector: Any  # np.ndarray | list[float] | None
    confidence: float = 1.0
    backend: str = "mock"


class FaceConsistencyService:
    """Compute ArcFace embeddings and cross-episode similarity matrix."""

    def __init__(self, *, model_root: str | Path | None = None) -> None:
        self._model_root = str(model_root or "/opt/insightface/models")
        self._insight_app: Any | None = None
        self._backend = "mock"
        self._init_insight()

    def _init_insight(self) -> None:
        try:
            from insightface.app import FaceAnalysis  # type: ignore[import-not-found]

            self._insight_app = FaceAnalysis(name="buffalo_l", root=self._model_root)
            self._insight_app.prepare(ctx_id=-1, det_size=(640, 640))
            self._backend = "insightface"
        except Exception:  # noqa: BLE001
            self._insight_app = None
            self._backend = "mock"

    @property
    def backend(self) -> str:
        return self._backend

    def compute_embedding_for_video(
        self,
        video_path: str | Path,
        *,
        char_id: str,
        episode_id: str,
        n_frames: int = 5,
    ) -> list[FaceEmbedding]:
        """Extract n frames from the video, compute embeddings for the largest face."""
        path = Path(video_path)
        if not path.exists():
            return []
        frames = _sample_frames(path, n=n_frames)
        if not frames:
            return []
        out: list[FaceEmbedding] = []
        for i, frame_bytes in enumerate(frames):
            vec, conf = self._embed_face(frame_bytes)
            out.append(
                FaceEmbedding(
                    char_id=char_id,
                    episode_id=episode_id,
                    frame_idx=i,
                    vector=vec,
                    confidence=conf,
                    backend=self._backend,
                )
            )
        return out

    def _embed_face(self, frame_bytes: bytes) -> tuple[Any, float]:
        if self._insight_app is not None and HAS_NUMPY:
            try:
                import cv2  # type: ignore[import-not-found]

                buf = np.frombuffer(frame_bytes, dtype=np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img is None:
                    return self._mock_embed(frame_bytes)
                faces = self._insight_app.get(img)
                if not faces:
                    return self._mock_embed(frame_bytes)
                f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
                vec = f.normed_embedding.astype("float32")
                conf = float(getattr(f, "det_score", 1.0))
                return vec, conf
            except Exception:  # noqa: BLE001
                pass
        return self._mock_embed(frame_bytes)

    def _mock_embed(self, frame_bytes: bytes) -> tuple[Any, float]:
        """Hash-based deterministic 64-d vector — for offline tests only."""
        h = hashlib.sha256(frame_bytes).digest()
        if HAS_NUMPY:
            arr = np.frombuffer(h[: 64] * 8, dtype=np.uint8).astype("float32") / 255.0
            arr = arr - arr.mean()
            norm = float(np.linalg.norm(arr)) or 1.0
            return arr / norm, 0.5
        # plain list
        return [b / 255.0 for b in h[:64]], 0.5

    @staticmethod
    def cosine(a: Any, b: Any) -> float:
        if HAS_NUMPY:
            try:
                aa = np.asarray(a, dtype="float32")
                bb = np.asarray(b, dtype="float32")
                n = (np.linalg.norm(aa) * np.linalg.norm(bb)) or 1.0
                return float(np.dot(aa, bb) / n)
            except Exception:  # noqa: BLE001
                return 0.0
        # python fallback
        try:
            num = sum(x * y for x, y in zip(a, b, strict=False))
            da = sum(x * x for x in a) ** 0.5
            db = sum(y * y for y in b) ** 0.5
            return float(num / ((da * db) or 1.0))
        except Exception:  # noqa: BLE001
            return 0.0

    def cross_episode_matrix(
        self,
        embeddings: dict[str, list[FaceEmbedding]],
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Build {char_id: {ep_a: {ep_b: mean_cosine}}}."""
        out: dict[str, dict[str, dict[str, float]]] = {}
        by_char: dict[str, dict[str, list[FaceEmbedding]]] = {}
        for char_id, items in embeddings.items():
            by_char.setdefault(char_id, {})
            for it in items:
                by_char[char_id].setdefault(it.episode_id, []).append(it)
        for char_id, by_ep in by_char.items():
            eps = sorted(by_ep.keys())
            out[char_id] = {}
            for a in eps:
                out[char_id][a] = {}
                for b in eps:
                    sims: list[float] = []
                    for ea in by_ep[a]:
                        for eb in by_ep[b]:
                            if ea.vector is None or eb.vector is None:
                                continue
                            sims.append(self.cosine(ea.vector, eb.vector))
                    out[char_id][a][b] = float(sum(sims) / len(sims)) if sims else 1.0 if a == b else 0.0
        return out

    @staticmethod
    def arcface_min(matrix: dict[str, dict[str, dict[str, float]]]) -> float:
        """Minimum cross-episode (a≠b) similarity across all characters."""
        vals: list[float] = []
        for char_data in matrix.values():
            for a, row in char_data.items():
                for b, v in row.items():
                    if a == b:
                        continue
                    vals.append(v)
        return float(min(vals)) if vals else 1.0

    @staticmethod
    def arcface_summary(matrix: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
        per_char: dict[str, dict[str, float]] = {}
        for char_id, rows in matrix.items():
            vals = [v for a, row in rows.items() for b, v in row.items() if a != b]
            if not vals:
                continue
            per_char[char_id] = {
                "min": float(min(vals)),
                "mean": float(sum(vals) / len(vals)),
                "max": float(max(vals)),
                "n_pairs": len(vals),
            }
        return per_char


def _sample_frames(video: Path, *, n: int = 5) -> list[bytes]:
    """ffmpeg uniform frame sampler → list of JPEG bytes (no base64)."""
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True, text=True, check=False, timeout=15,
        )
        try:
            dur = float(probe.stdout.strip())
        except ValueError:
            dur = 5.0
        if dur <= 0:
            dur = 5.0
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        dur = 5.0

    if n < 1:
        n = 1
    if n == 1:
        ts = [dur / 2.0]
    else:
        step = dur / (n + 1)
        ts = [step * (i + 1) for i in range(n)]

    frames: list[bytes] = []
    for t in ts:
        with contextlib.suppress(subprocess.SubprocessError, OSError, FileNotFoundError):
            r = subprocess.run(
                [
                    "ffmpeg", "-v", "error",
                    "-ss", f"{t:.3f}",
                    "-i", str(video),
                    "-frames:v", "1",
                    "-q:v", "3",
                    "-f", "image2pipe",
                    "-vcodec", "mjpeg",
                    "pipe:1",
                ],
                capture_output=True, check=False, timeout=30,
            )
            if r.returncode == 0 and r.stdout:
                frames.append(r.stdout)
    return frames


__all__ = ["FaceConsistencyService", "FaceEmbedding"]
