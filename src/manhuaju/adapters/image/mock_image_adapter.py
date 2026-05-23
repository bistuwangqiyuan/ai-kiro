"""Mock image adapter — Pillow-rendered placeholders for offline/CI use.

Mirrors the surface of `RealSeedreamAdapter` / `RealJimengAdapter` so the
factory can swap them transparently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from manhuaju.adapters.image.real_seedream_adapter import GeneratedImage


@dataclass
class _Spec:
    width: int = 864
    height: int = 1152


class MockImageAdapter:
    name = "MockImageAdapter"
    provider = "mock_image"

    def __init__(self, *, artefacts_root: Path) -> None:
        self.artefacts_root = artefacts_root
        self.artefacts_root.mkdir(parents=True, exist_ok=True)

    # ----- API parity with Real adapters -----
    def generate(
        self,
        *,
        prompt: str,
        num_images: int = 4,
        aspect_ratio: str = "3:4",
        seed: int = 0,
        upload_to_tos: bool = False,  # noqa: ARG002
        prefix: str = "mock",
    ) -> list[GeneratedImage]:
        spec = _aspect_to_spec(aspect_ratio)
        out: list[GeneratedImage] = []
        for i in range(num_images):
            local = self.artefacts_root / f"{prefix}_{i:02d}_{_hash(prompt, seed, i)}.png"
            self._render(local, prompt=prompt, idx=i, seed=seed + i, spec=spec)
            out.append(
                GeneratedImage(
                    local_path=local,
                    public_url=local.absolute().as_uri(),
                    width=spec.width,
                    height=spec.height,
                    seed=seed + i,
                    prompt=prompt,
                    model="mock-pillow",
                    provider=self.provider,
                    bytes=local.stat().st_size,
                )
            )
        return out

    def generate_group(self, **kwargs):  # type: ignore[no-untyped-def]
        return self.generate(**kwargs)

    def generate_with_reference(self, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("reference_images", None)
        return self.generate(**kwargs)

    # ----- internals -----
    def _render(self, dest: Path, *, prompt: str, idx: int, seed: int, spec: _Spec) -> None:
        h = int(hashlib.md5(f"{prompt}:{seed}:{idx}".encode()).hexdigest(), 16)
        hue = (h % 360) / 360.0
        from colorsys import hsv_to_rgb

        r, g, b = (int(c * 255) for c in hsv_to_rgb(hue, 0.55, 0.78))
        img = Image.new("RGB", (spec.width, spec.height), (r, g, b))
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [(20, 20), (spec.width - 20, spec.height - 20)],
            outline=(255, 255, 255),
            width=4,
        )
        text = f"#{idx + 1}\n{prompt[:60]}\nseed={seed}"
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None
        draw.multiline_text((40, 40), text, fill=(255, 255, 255), font=font, spacing=6)
        img.save(dest, format="PNG", optimize=True)


def _aspect_to_spec(ar: str) -> _Spec:
    table = {
        "9:16": _Spec(768, 1344),
        "3:4": _Spec(864, 1152),
        "1:1": _Spec(1024, 1024),
        "4:3": _Spec(1152, 864),
        "16:9": _Spec(1344, 768),
    }
    return table.get(ar, _Spec(1024, 1024))


def _hash(*parts: object) -> str:
    return hashlib.md5(":".join(str(p) for p in parts).encode()).hexdigest()[:6]
