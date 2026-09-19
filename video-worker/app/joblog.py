import json
from datetime import datetime, timezone


def log_event(job_id: str, stage: str, **fields) -> None:
    """job_id ile korele edilmiş tek satır JSON log basar (docker compose logs'ta okunur)."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "stage": stage,
        **fields,
    }
    try:
        print(json.dumps(record, ensure_ascii=False), flush=True)
    except UnicodeEncodeError:
        print(json.dumps(record, ensure_ascii=True), flush=True)
