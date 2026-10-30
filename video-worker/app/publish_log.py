import json
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


def load_recent_entries(log_path: str, since_iso: str) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [e for e in entries if e["published_at"] >= since_iso]
