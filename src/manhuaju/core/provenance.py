"""Provenance hash-chain writer (REQ-NFR-PROV-001/003).

Chain rule:
    chain_self_sha_n = sha256( (chain_self_sha_{n-1} or "") || canonical_json(body_n) )

`body_n` is the canonical-JSON of the Provenance payload **excluding**
`chain_prev_sha` and `chain_self_sha` (those are the chain glue, not part of
the body). This keeps the hash stable independently of how datetimes are
formatted on round-trip, because we always serialise via the same canonical
function.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manhuaju.schemas import Provenance, now
from manhuaju.utils.canonical_json import to_canonical

BODY_FIELDS = (
    "artefact_uri",
    "sha256",
    "size",
    "producer_agent",
    "model",
    "model_version",
    "seed",
    "parent_artefact_uri",
    "prompt_sha256",
    "response_sha256",
    "created_at",
)


class ProvenanceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = root / "manifest.jsonl"
        if not self.manifest_path.exists():
            self.manifest_path.write_text("", encoding="utf-8")
        self._last_chain: str | None = None

    @staticmethod
    def _hash(prev: str | None, body_canonical: str) -> str:
        h = hashlib.sha256()
        h.update((prev or "").encode("utf-8"))
        h.update(body_canonical.encode("utf-8"))
        return h.hexdigest()

    def record(
        self,
        *,
        artefact_uri: str,
        sha256: str,
        size: int,
        producer_agent: str,
        model: str = "mock",
        model_version: str = "v1",
        seed: int = 0,
        parent_artefact_uri: str | None = None,
        prompt_sha256: str | None = None,
        response_sha256: str | None = None,
    ) -> Provenance:
        # Build prov with placeholder chain values, then re-emit serialised body
        # to compute the hash.
        prov_partial = Provenance(
            artefact_uri=artefact_uri,
            sha256=sha256,
            size=size,
            producer_agent=producer_agent,
            model=model,
            model_version=model_version,
            seed=seed,
            parent_artefact_uri=parent_artefact_uri,
            prompt_sha256=prompt_sha256,
            response_sha256=response_sha256,
            created_at=now(),
            chain_prev_sha=self._last_chain,
            chain_self_sha="",
        )
        dumped = prov_partial.model_dump(mode="json")
        body = {k: dumped[k] for k in BODY_FIELDS}
        chain_self = self._hash(self._last_chain, to_canonical(body))
        # Frozen=True: rebuild with computed chain.
        prov = prov_partial.model_copy(update={"chain_self_sha": chain_self})

        with self.manifest_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(prov.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                + "\n"
            )
        self._last_chain = chain_self
        return prov

    def verify(self) -> bool:
        prev: str | None = None
        if not self.manifest_path.exists():
            return True
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            body = {k: entry[k] for k in BODY_FIELDS}
            recomputed = self._hash(prev, to_canonical(body))
            if recomputed != entry["chain_self_sha"]:
                return False
            prev = entry["chain_self_sha"]
        return True
