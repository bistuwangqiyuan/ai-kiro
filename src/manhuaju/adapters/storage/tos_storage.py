"""Volcengine TOS (Tinder Object Storage) adapter — v4 fast-path.

提供「上传 → 生成 24h 预签名 URL」给小云雀「有参考」接口使用。
其他用途：参考图入库、成片归档、封面 CDN 分发。

Graceful fallback：若未安装 `tos` SDK 或未配 AK/SK，
则降级回 `LocalFSStorage`，把本地路径以 file:// URL 返回。
"""

from __future__ import annotations

import hashlib
import mimetypes
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manhuaju.core.provider_settings import ProviderSettings


@dataclass
class TOSUploadResult:
    key: str
    public_url: str
    presigned_url: str
    etag: str
    bytes: int


class TOSStorage:
    """Thread-safe TOS client wrapper. Idempotent uploads by content-hash key."""

    name = "VolcengineTOSStorage"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        prefix: str = "manhuaju",
        local_fallback_root: Path | None = None,
    ) -> None:
        self._s = settings
        self._prefix = prefix.strip("/")
        self._fallback_root = Path(local_fallback_root or Path("./api_data/_local_tos"))
        self._fallback_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._client: Any = None
        self._client_kind: str = "none"
        self._cache: dict[str, TOSUploadResult] = {}
        self._initialise()

    def _initialise(self) -> None:
        if not self._s.has_tos:
            self._client_kind = "local"
            return
        try:
            import tos  # type: ignore[import-untyped]

            self._client = tos.TosClientV2(
                self._s.tos.ak,
                self._s.tos.sk,
                self._s.tos.endpoint,
                self._s.tos.region,
            )
            self._client_kind = "tos"
        except ImportError:
            self._client_kind = "local"

    @property
    def configured(self) -> bool:
        return self._client_kind == "tos"

    # ----- core API -----
    def upload_file(
        self,
        local_path: str | Path,
        *,
        key: str | None = None,
        content_type: str | None = None,
    ) -> TOSUploadResult:
        """Upload a local file to TOS (or local fallback). Returns metadata + URLs."""
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"TOS upload source missing: {path}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()[:16]
        ext = path.suffix or ".bin"
        final_key = key or f"{self._prefix}/{digest}{ext}"

        with self._lock:
            if final_key in self._cache:
                return self._cache[final_key]

        ct = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        if self._client_kind == "tos":
            try:
                import tos  # type: ignore[import-untyped]  # noqa: F401

                self._client.put_object(
                    bucket=self._s.tos.bucket,
                    key=final_key,
                    content=data,
                    content_type=ct,
                )
                public_url = self._s.tos.public_url(final_key)
                presigned = self._presign_internal(final_key)
                result = TOSUploadResult(
                    key=final_key,
                    public_url=public_url,
                    presigned_url=presigned,
                    etag=digest,
                    bytes=len(data),
                )
                with self._lock:
                    self._cache[final_key] = result
                return result
            except Exception:
                # Fall through to local
                self._client_kind = "local"

        # local fallback
        dest = self._fallback_root / final_key.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        # Local fallback URL is file:// (xiaoyunque cannot consume; in mock/hybrid this is fine).
        public_url = dest.absolute().as_uri()
        result = TOSUploadResult(
            key=final_key,
            public_url=public_url,
            presigned_url=public_url,
            etag=digest,
            bytes=len(data),
        )
        with self._lock:
            self._cache[final_key] = result
        return result

    def upload_bytes(
        self,
        data: bytes,
        *,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> TOSUploadResult:
        digest = hashlib.sha256(data).hexdigest()[:16]
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        if self._client_kind == "tos":
            try:
                self._client.put_object(
                    bucket=self._s.tos.bucket,
                    key=key,
                    content=data,
                    content_type=content_type,
                )
                public_url = self._s.tos.public_url(key)
                presigned = self._presign_internal(key)
                result = TOSUploadResult(
                    key=key,
                    public_url=public_url,
                    presigned_url=presigned,
                    etag=digest,
                    bytes=len(data),
                )
                with self._lock:
                    self._cache[key] = result
                return result
            except Exception:
                self._client_kind = "local"

        dest = self._fallback_root / key.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        public_url = dest.absolute().as_uri()
        result = TOSUploadResult(
            key=key,
            public_url=public_url,
            presigned_url=public_url,
            etag=digest,
            bytes=len(data),
        )
        with self._lock:
            self._cache[key] = result
        return result

    def get_presigned_url(self, key: str, *, expires_s: int = 86400) -> str:
        if self._client_kind == "tos":
            try:
                return self._presign_internal(key, expires_s=expires_s)
            except Exception:
                pass
        # Local fallback returns the file URI directly
        local = self._fallback_root / key.lstrip("/")
        return local.absolute().as_uri()

    def _presign_internal(self, key: str, *, expires_s: int = 86400) -> str:
        try:
            import tos  # type: ignore[import-untyped]

            req = tos.PreSignedURLInput(
                http_method=tos.HttpMethodType.Http_Method_Get,
                bucket=self._s.tos.bucket,
                key=key,
                expires=expires_s,
            )
            resp = self._client.pre_signed_url(req)
            return str(resp.signed_url)
        except Exception:
            return self._s.tos.public_url(key)

    def batch_upload(self, items: list[tuple[str | Path, str | None]]) -> list[TOSUploadResult]:
        """Upload many files; returns list in input order. (Sequential, simple.)"""
        out: list[TOSUploadResult] = []
        for src, key in items:
            out.append(self.upload_file(src, key=key))
        return out
