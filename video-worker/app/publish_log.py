import json
from datetime import datetime, timezone
from pathlib import Path

from app.jsonstore import locked_json


def file_sha256(path: str, *, chunk_size: int = 1 << 20) -> str:
    """Video dosyasının içerik özeti — onayın hangi dosyaya verildiğini bağlar."""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_publish_log(log_path: str, entry: dict) -> None:
    with locked_json(Path(log_path), []) as entries:
        entries.append(entry)


def build_publish_entry(
    *,
    job_id: str,
    title: str,
    kind: str,
    results: list[dict],
    approved_sha256: str = "",
    published_at: str | None = None,
) -> dict:
    """Yayın kaydının tek şeması — yayın ile üretim işini birleştirir.

    Ölçüm (düzeltme öncesi): kayıt yalnızca `published_at, title, kind,
    platforms` taşıyordu. `job_id` yoktu, dolayısıyla "bu yayın hangi işin,
    hangi manifestin, hangi onayın ürünü?" sorusu cevaplanamıyordu ve üretimde
    yazılan `DOCUMENTARY_ENGINE_V2_MANIFEST_<job_id>.json` hiçbir kayda
    bağlanmıyordu (manifest okuyan tüketici: 0).

    `approved_sha256` bilinçli olarak kayda giriyor: onayın hangi dosyaya
    verildiği, sonradan doğrulanabilir tek kanıt.
    """
    return {
        "published_at": published_at
        or datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "title": title,
        "kind": kind,
        "approved_sha256": approved_sha256 or "",
        "platforms": {r["platform"]: r for r in results},
    }


def load_recent_entries(log_path: str, since_iso: str) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(entries, list):
        return []
    # Eski kayıtlarda job_id/approved_sha256 yok; filtre onları dışlamamalı.
    return [e for e in entries if isinstance(e, dict) and e.get("published_at", "") >= since_iso]
