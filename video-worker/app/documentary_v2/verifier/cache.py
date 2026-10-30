"""Verification cache — key includes content fingerprint + intent + model + prompt."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.documentary_v2.schemas import VisualVerification
from app.documentary_v2.verifier.reason_codes import PROMPT_VERSION


def verification_cache_key(
    *,
    content_fingerprint: str,
    intent_signature: str,
    verifier_provider: str,
    verifier_model: str,
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = "1",
) -> str:
    payload = {
        "fp": content_fingerprint,
        "intent": intent_signature,
        "provider": verifier_provider,
        "model": verifier_model,
        "prompt": prompt_version,
        "schema": schema_version,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


class VerificationCache:
    def __init__(self, root: Path | str | None = None, ttl_sec: float = 86400 * 14) -> None:
        self.root = Path(root) if root else None
        self.ttl_sec = ttl_sec
        self._mem: dict[str, tuple[float, dict]] = {}

    def get(self, key: str) -> VisualVerification | None:
        now = time.time()
        if key in self._mem:
            ts, data = self._mem[key]
            if now - ts <= self.ttl_sec:
                return _from_cache_dict(data)
            del self._mem[key]
        if self.root:
            path = self.root / f"{key}.json"
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if now - float(data.get("cached_at_epoch", 0)) <= self.ttl_sec:
                        return _from_cache_dict(data.get("verification") or {})
                except Exception:
                    return None
        return None

    def set(self, key: str, verification: VisualVerification) -> None:
        now = time.time()
        payload = verification.to_dict()
        self._mem[key] = (now, payload)
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / f"{key}.json").write_text(
                json.dumps(
                    {
                        "cached_at_epoch": now,
                        "verified_at": payload.get("verified_at"),
                        "verification": payload,
                    },
                    ensure_ascii=False,
                )[:400000],
                encoding="utf-8",
            )


def _from_cache_dict(d: dict) -> VisualVerification:
    # Only pass known fields
    fields = {f.name for f in VisualVerification.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in d.items() if k in fields}
    if "verification_id" not in kwargs:
        kwargs["verification_id"] = d.get("verification_id") or "cached"
    return VisualVerification(**kwargs)
