import json
import os
import tempfile
import threading
from pathlib import Path

# Aynı süreçteki eşzamanlı yayınlar bu dosyaya oku-değiştir-yaz yapıyor; kilitsiz
# hâlde kayıtlar kayboluyor ve dosya bozuk JSON'a dönüşebiliyordu.
_log_lock = threading.Lock()


def file_sha256(path: str, *, chunk_size: int = 1 << 20) -> str:
    """Video dosyasının içerik özeti — onayın hangi dosyaya verildiğini bağlar."""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload) -> None:
    """Aynı dizine yazıp atomik olarak yerine koyar; okuyucu asla yarım dosya görmez."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def append_publish_log(log_path: str, entry: dict) -> None:
    path = Path(log_path)
    with _log_lock:
        if path.is_file():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Bozulmuş dosyayı kaybetmek yerine yanına alıp temiz başla.
                path.with_suffix(path.suffix + ".corrupt").write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8"
                )
                entries = []
        else:
            entries = []
        entries.append(entry)
        _write_json_atomic(path, entries)


def load_recent_entries(log_path: str, since_iso: str) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [e for e in entries if e["published_at"] >= since_iso]
