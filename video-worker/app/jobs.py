"""Minimal SQLite job store for video/image pipeline states.

States: queued | generating | awaiting_approval | publishing | failed | done

Telegram UX still dual-writes `pending.json` for backward compatibility;
this module is the durable source of truth for job lifecycle.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

JOB_STATES = (
    "queued",
    "generating",
    "awaiting_approval",
    "publishing",
    "failed",
    "done",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'video',
    state TEXT NOT NULL,
    topic TEXT,
    title TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
"""


def _db_path(media_dir: str | Path) -> Path:
    return Path(media_dir) / "jobs.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(media_dir: str | Path) -> Iterator[sqlite3.Connection]:
    path = _db_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_job(
    media_dir: str | Path,
    job_id: str,
    *,
    kind: str = "video",
    state: str = "generating",
    topic: str | None = None,
    title: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in JOB_STATES:
        raise ValueError(f"invalid job state: {state}")
    now = _utc_now()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with _connect(media_dir) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, kind, state, topic, title, payload_json, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind=excluded.kind,
                state=excluded.state,
                topic=excluded.topic,
                title=excluded.title,
                payload_json=excluded.payload_json,
                error=NULL,
                updated_at=excluded.updated_at
            """,
            (job_id, kind, state, topic, title, payload_json, now, now),
        )
    return get_job(media_dir, job_id)  # type: ignore[return-value]


def update_job(
    media_dir: str | Path,
    job_id: str,
    *,
    state: str | None = None,
    title: str | None = None,
    topic: str | None = None,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    row = get_job(media_dir, job_id)
    if row is None:
        return None
    if state is not None and state not in JOB_STATES:
        raise ValueError(f"invalid job state: {state}")
    new_state = state if state is not None else row["state"]
    new_title = title if title is not None else row.get("title")
    new_topic = topic if topic is not None else row.get("topic")
    new_payload = payload if payload is not None else row.get("payload") or {}
    # Explicit error=None clears; omit by passing ... we use a sentinel via kwargs presence
    new_error = error if error is not None else row.get("error")
    if error == "":
        new_error = None
    with _connect(media_dir) as conn:
        conn.execute(
            """
            UPDATE jobs
            SET state=?, title=?, topic=?, payload_json=?, error=?, updated_at=?
            WHERE id=?
            """,
            (
                new_state,
                new_title,
                new_topic,
                json.dumps(new_payload, ensure_ascii=False),
                new_error,
                _utc_now(),
                job_id,
            ),
        )
    return get_job(media_dir, job_id)


def get_job(media_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    with _connect(media_dir) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def get_awaiting_approval(media_dir: str | Path) -> dict[str, Any] | None:
    """Most recent job waiting for Telegram approve/reject."""
    with _connect(media_dir) as conn:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE state='awaiting_approval'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def has_blocking_job(media_dir: str | Path) -> bool:
    """True if a new generate should be refused (pending human approval)."""
    with _connect(media_dir) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM jobs
            WHERE state IN ('generating', 'awaiting_approval', 'publishing')
            LIMIT 1
            """
        ).fetchone()
    return row is not None


def mark_done(media_dir: str | Path, job_id: str) -> None:
    update_job(media_dir, job_id, state="done", error="")


def mark_failed(media_dir: str | Path, job_id: str, error: str) -> None:
    update_job(media_dir, job_id, state="failed", error=error)


def clear_awaiting(media_dir: str | Path, job_id: str | None = None) -> None:
    """Move awaiting_approval or publishing job(s) to done (after publish/reject).

    Publish success path sets state=publishing before uploads; clearing must
    include that state or has_blocking_job stays True forever (409 on /generate).
    """
    clearable = ("awaiting_approval", "publishing")
    with _connect(media_dir) as conn:
        if job_id:
            conn.execute(
                "UPDATE jobs SET state='done', updated_at=? "
                "WHERE id=? AND state IN ('awaiting_approval', 'publishing')",
                (_utc_now(), job_id),
            )
        else:
            placeholders = ",".join("?" for _ in clearable)
            conn.execute(
                f"UPDATE jobs SET state='done', updated_at=? WHERE state IN ({placeholders})",
                (_utc_now(), *clearable),
            )


def write_pending_mirror(media_dir: str | Path, payload: dict[str, Any]) -> None:
    """Dual-write pending.json so existing Telegram/n8n paths keep working."""
    media = Path(media_dir)
    media.mkdir(parents=True, exist_ok=True)
    (media / "pending.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def read_pending_payload(media_dir: str | Path) -> dict[str, Any] | None:
    """Prefer SQLite awaiting_approval payload; fall back to pending.json."""
    job = get_awaiting_approval(media_dir)
    if job and isinstance(job.get("payload"), dict) and job["payload"]:
        payload = dict(job["payload"])
        payload.setdefault("job_id", job["id"])
        return payload
    pending_path = Path(media_dir) / "pending.json"
    if pending_path.is_file():
        return json.loads(pending_path.read_text(encoding="utf-8"))
    return None


def clear_pending_mirror(media_dir: str | Path, job_id: str | None = None) -> None:
    clear_awaiting(media_dir, job_id)
    Path(media_dir, "pending.json").unlink(missing_ok=True)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
    except json.JSONDecodeError:
        data["payload"] = {}
    return data
