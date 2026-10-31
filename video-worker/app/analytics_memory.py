"""Analytics memory for winning hooks — scaffolding for ENABLE_ANALYTICS_MEMORY.

Live vs stub
------------
LIVE (when ENABLE_ANALYTICS_MEMORY=true and YouTube creds work):
  - ``channel_growth.get_winning_context_for_prompt`` injects top YT title/views
    into the LLM prompt (existing path in pipeline).

STUB (this module — always safe, no YouTube required):
  - ``load_winning_hooks`` / ``store_winning_hook`` read/write a local JSON ledger
    under MEDIA_DIR (default ``winning_hooks.json``).
  - ``format_hook_memory_context`` turns stored hooks into a short prompt addendum.
  - Does NOT score retention or call YouTube yet — only persists hooks the pipeline
    (or a future approve handler) chooses to record.

Wire: config.ENABLE_ANALYTICS_MEMORY gates both live YT context and stub injection.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_NAME = "winning_hooks.json"
MAX_STORED_HOOKS = 40


def _ledger_path(media_dir: str | Path | None = None) -> Path:
    root = Path(media_dir or config.MEDIA_DIR)
    return root / DEFAULT_LEDGER_NAME


def load_winning_hooks(media_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Stub store: previously recorded winning hooks (newest last).

    İki kaynak birleştiriliyor:

    1. `winning_hooks.json` — operatörün elle işaretlediği hook'lar.
    2. `performance_ledger.json` — ÖLÇÜLMÜŞ performanstan türetilen hook'lar.

    İkinci kaynak ölçümün eklenmesiyle geldi: önce yalnızca birinci vardı ve
    onu yazan hiçbir kod yoktu (ölçüm: `store_winning_hook` çağrısı 0), yani
    hafıza prompt'a her zaman 0 karakter ekliyordu. Ölçülen hook'lar
    `views`/`samples` alanlarıyla geliyor; böylece çağıran sıralayabiliyor.
    """
    path = _ledger_path(media_dir)
    hooks: list[dict[str, Any]] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("winning_hooks ledger unreadable: %s", exc)
            data = None
        if data is not None:
            stored = data.get("hooks") if isinstance(data, dict) else data
            if isinstance(stored, list):
                hooks = [h for h in stored if isinstance(h, dict) and h.get("hook")]

    measured = _measured_hooks(media_dir)
    if measured:
        seen = {(h.get("hook") or "").strip().lower() for h in hooks}
        hooks.extend(
            h for h in measured
            if (h.get("hook") or "").strip().lower() not in seen
        )
    return hooks


def _measured_hooks(media_dir: str | Path | None) -> list[dict[str, Any]]:
    """Performans defterinden en iyi hook'lar; defter yoksa boş liste."""
    try:
        from app.performance_ledger import best_hooks

        return best_hooks(Path(media_dir or config.MEDIA_DIR))
    except Exception:  # noqa: BLE001 - hafıza asla üretimi düşürmemeli
        return []


def store_winning_hook(
    hook: str,
    *,
    topic: str = "",
    title: str = "",
    job_id: str = "",
    media_dir: str | Path | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Stub store: append a hook the operator marked as winning (or A/B pick)."""
    text = (hook or "").strip()
    if not text:
        return
    path = _ledger_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = load_winning_hooks(media_dir)
    entry: dict[str, Any] = {
        "hook": text,
        "topic": topic,
        "title": title,
        "job_id": job_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        entry.update(extra)
    entries.append(entry)
    entries = entries[-MAX_STORED_HOOKS:]
    # Kilitli + atomik yazma: eşzamanlı onay/ölçüm aynı dosyaya yazabiliyor.
    # Ölçüm (paylaşılan desende): kilitsiz oku-değiştir-yaz 40 kayıttan 35'ini
    # kaybediyordu — bu defter de aynı riski taşıyordu.
    from app.jsonstore import write_atomic

    write_atomic(path, {"hooks": entries})


def format_hook_memory_context(
    media_dir: str | Path | None = None,
    *,
    max_hooks: int = 5,
) -> str:
    """Stub → prompt: list recent winning hooks so the LLM diversifies away from them."""
    hooks = load_winning_hooks(media_dir)
    if not hooks:
        return ""
    recent = hooks[-max_hooks:]
    lines = [
        "",
        "# Historical Winning Hooks (local ledger — stub analytics memory):",
        "Prefer a DIFFERENT curiosity angle than these past winners:",
    ]
    for item in recent:
        lines.append(f"- {item['hook']}")
    lines.append(
        "Do NOT reuse the same template opener (e.g. 'Nobody tells you…')."
    )
    return "\n".join(lines) + "\n"


def pick_hook_alternative(
    alternatives: list[str],
    *,
    media_dir: str | Path | None = None,
) -> str:
    """Pick one hook: prefer alternatives that are not exact matches of recent winners."""
    cleaned = [a.strip() for a in alternatives if isinstance(a, str) and a.strip()]
    if not cleaned:
        return ""
    winners = {
        (h.get("hook") or "").strip().lower()
        for h in load_winning_hooks(media_dir)
    }
    for alt in cleaned:
        if alt.lower() not in winners:
            return alt
    return cleaned[0]
