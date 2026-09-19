import json
from pathlib import Path


def append_publish_log(log_path: str, entry: dict) -> None:
    path = Path(log_path)
    if path.is_file():
        entries = json.loads(path.read_text(encoding="utf-8"))
    else:
        entries = []
    entries.append(entry)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_recent_entries(log_path: str, since_iso: str) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [e for e in entries if e["published_at"] >= since_iso]
