"""Diagnostic: probe each LLM provider individually and print error body."""

from __future__ import annotations

import time

import httpx

from manhuaju.core.provider_settings import get_provider_settings


def main() -> None:
    settings = get_provider_settings()
    eligible = [e for e in settings.llm_endpoints if e.enabled and e.api_key]
    body = {
        "messages": [{"role": "user", "content": "say hi"}],
        "max_tokens": 16,
        "temperature": 0.0,
    }
    for ep in eligible:
        url = f"{ep.base_url.rstrip('/')}/chat/completions"
        b = {**body, "model": ep.default_model}
        t0 = time.time()
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {ep.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=b,
                )
            dt = time.time() - t0
            print(f"[{ep.name:12s}] {ep.default_model:38s} → HTTP {r.status_code} ({dt:.1f}s)")
            if r.status_code != 200:
                print(f"     body: {r.text[:300]}")
            else:
                content = r.json()["choices"][0]["message"]["content"][:80]
                print(f"     ok: {content!r}")
        except Exception as e:  # noqa: BLE001
            print(f"[{ep.name:12s}] {ep.default_model} → ERR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
