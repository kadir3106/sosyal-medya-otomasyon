"""Persist ProductionManifest / telemetry (Stage A)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.documentary_v2.adapters import build_production_manifest_from_legacy
from app.documentary_v2.schemas import ProductionManifest

logger = logging.getLogger(__name__)


def write_production_manifest(
    media_dir: str | Path,
    manifest: ProductionManifest,
) -> Path:
    media = Path(media_dir)
    media.mkdir(parents=True, exist_ok=True)
    path = media / f"DOCUMENTARY_ENGINE_V2_MANIFEST_{manifest.job_id}.json"
    payload = manifest.to_dict()
    leaks = ProductionManifest.assert_no_secrets(payload)
    if leaks:
        logger.error("ProductionManifest secret-like keys blocked: %s", leaks)
        for key_path in leaks:
            # Redact rather than write secrets
            _redact(payload, key_path)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)[:500000],
        encoding="utf-8",
    )
    return path


def _redact(obj: Any, dotted: str) -> None:
    parts = dotted.replace("]", "").replace("[", ".").split(".")
    cur = obj
    for i, p in enumerate(parts):
        if not p:
            continue
        if i == len(parts) - 1:
            if isinstance(cur, dict) and p in cur:
                cur[p] = "[REDACTED]"
            return
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            cur = cur[int(p)]
        else:
            return
        if cur is None:
            return


def emit_legacy_job_manifest(
    *,
    media_dir: str | Path,
    job_id: str,
    topic: str,
    script_data: dict | None = None,
    quality: dict | None = None,
    result: dict | None = None,
    audio_duration: float | None = None,
) -> Path | None:
    """Non-invasive: write joinable manifest for every completed generate."""
    try:
        manifest = build_production_manifest_from_legacy(
            job_id=job_id,
            topic=topic,
            script_data=script_data,
            quality=quality,
            result=result,
            audio_duration=audio_duration,
        )
        return write_production_manifest(media_dir, manifest)
    except Exception as exc:
        logger.warning("Stage A manifest write failed: %s", exc)
        return None
