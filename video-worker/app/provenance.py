"""Bir yayının izini sür: onay → dosya → iş → üretim manifesti.

Ölçülen kopukluk (düzeltme öncesi): yayın kaydı `job_id` taşımıyordu ve
`DOCUMENTARY_ENGINE_V2_MANIFEST_<job_id>.json` dosyasını okuyan tek bir
tüketici yoktu. Sonuç: "bu yayın hangi script, hangi medya, hangi model ve
hangi onayla yapıldı?" sorusu cevaplanamıyordu — Faz 1'in çıkış kriteri.

Bu modül o sorunun cevabını tek bir sözlükte toplar. Sadece okur; hiçbir
durumu değiştirmez, hiçbir yayını tetiklemez.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app import jobs as job_store
from app.documentary_v2.telemetry import manifest_path, read_production_manifest


def trace_publication(
    media_dir: str | Path, entry: dict[str, Any]
) -> dict[str, Any]:
    """Bir yayın kaydını üretim işine ve manifestine bağlar.

    Eksik parçalar hata değil, `None` olarak döner: eski kayıtlarda `job_id`
    yok, bazı işlerde (legacy/curl akışı) manifest hiç yazılmamış olabilir.
    Çağıran `complete` alanına bakarak neyin eksik olduğunu görür.
    """
    job_id = str(entry.get("job_id") or "")
    media = Path(media_dir)

    job = job_store.get_job(media, job_id) if job_id else None
    manifest = read_production_manifest(media, job_id) if job_id else None

    trace: dict[str, Any] = {
        "job_id": job_id or None,
        "approved_sha256": entry.get("approved_sha256") or None,
        "manifest_path": str(manifest_path(media, job_id)) if job_id else None,
        "platforms": sorted((entry.get("platforms") or {}).keys()),
        "job": None,
        "manifest": None,
    }

    if job:
        payload = job.get("payload") or {}
        trace["job"] = {
            "state": job.get("state"),
            "topic": job.get("topic"),
            "title": job.get("title"),
            "video_sha256": payload.get("video_sha256"),
            "video_filename": payload.get("video_filename"),
            "final_script": payload.get("final_script"),
            "tts": (payload.get("quality") or {}).get("tts"),
            "engine": (payload.get("quality") or {}).get("engine"),
        }

    if manifest:
        trace["manifest"] = {
            "pipeline_mode": manifest.get("pipeline_mode"),
            "claims": len(manifest.get("claims") or []),
            "assets": len(manifest.get("assets") or []),
            "model_calls": len(manifest.get("model_calls") or []),
            "quality": len(manifest.get("quality") or []),
            "duration_sec": manifest.get("duration_sec"),
        }

    # Onay → dosya bağı: kayıttaki hash, işin payload'ındaki hash'le aynı olmalı.
    # Farklıysa yayın, onaylanandan başka bir dosyayla yapılmış demektir.
    approved = trace["approved_sha256"]
    produced = (trace["job"] or {}).get("video_sha256")
    trace["sha256_match"] = (
        None if not approved or not produced else approved == produced
    )
    trace["complete"] = bool(trace["job"] and trace["manifest"] and trace["sha256_match"])

    return trace
