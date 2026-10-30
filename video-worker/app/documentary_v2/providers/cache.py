"""Search result cache (metadata only — no secrets)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def cache_key(
    provider: str,
    query: str,
    *,
    filters: dict | None = None,
) -> str:
    payload = {
        "provider": provider,
        "query": (query or "").strip().lower(),
        "filters": filters or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class SearchCache:
    def __init__(self, root: Path | str | None = None, ttl_sec: float = 3600.0) -> None:
        self.root = Path(root) if root else None
        self.ttl_sec = ttl_sec
        self._mem: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.time()
        if key in self._mem:
            ts, val = self._mem[key]
            if now - ts <= self.ttl_sec:
                return val
            del self._mem[key]
        if self.root:
            path = self.root / f"{key}.json"
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if now - float(data.get("retrieved_at_epoch", 0)) <= self.ttl_sec:
                        return data.get("payload")
                except Exception:
                    return None
        return None

    def set(self, key: str, payload: Any) -> None:
        now = time.time()
        self._mem[key] = (now, payload)
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / f"{key}.json"
            path.write_text(
                json.dumps(
                    {
                        "retrieved_at_epoch": now,
                        "retrieved_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)
                        ),
                        "payload": payload,
                    },
                    ensure_ascii=False,
                )[:500000],
                encoding="utf-8",
            )
