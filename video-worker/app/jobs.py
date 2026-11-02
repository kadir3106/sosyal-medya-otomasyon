"""Minimal SQLite job store for video/image pipeline states.

States: queued | generating | awaiting_approval | publishing | failed | done

Telegram UX still dual-writes `pending.json` for backward compatibility;
this module is the durable source of truth for job lifecycle.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.jsonstore import write_atomic

logger = logging.getLogger(__name__)

# `pending.json` yazma/okuma/silme tek kilitten geçer. video-worker tek süreç
# olarak çalışıyor, yani kendi okuyucularımızı serileştirmek Windows'taki
# "hedefte açık tutamak varken os.replace engellenir" (WinError 5) sorununu
# süreç içinde tamamen kaldırıyor. Ölçüm: kilit olmadan 4 okuyucu + yazıcı
# altında retry'ın 5 denemesi de PermissionError ile tükendi. Süreç DIŞI
# tutamaklar (n8n, host araçları) için sınırlı retry hâlâ gerekli; onlar
# yüzünden yazma başarısız olursa istisna yükselir — sessizce yerinde yazmak
# yarım dosya riskini geri getirirdi.
_pending_lock = threading.Lock()

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


def new_job_id(now: datetime | None = None) -> str:
    """Saniye damgası + kısa rastgele sonek.

    Yalnızca saniye çözünürlüğü kullanıldığında aynı saniyedeki iki istek aynı
    kimliği alıyordu; bu da aynı `work_dir`'e yazıp ara dosyaları birbirinin
    üzerine ezmek demekti. Ölçüm: iki istek de `20261031-070512` aldı, jobs
    tablosunda tek satır kaldı.

    Sonek 6 hex karakter: biçim `20261031-070512-a1b2c3`. Telegram
    `callback_data` sınırı 64 bayt — bu biçim 21 bayt, bolca yer var.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


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


def claim_for_publish(
    media_dir: str | Path, job_id: str, *, kind: str = "video"
) -> bool:
    """Atomically move a job to 'publishing'; False if it is already publishing/done.

    Publishing is public and irreversible, so a duplicate /publish (n8n retry,
    Telegram double-callback) must not upload twice. 'failed' stays claimable so
    the "Tekrar dene" button still works. An unknown job is still let through:
    image and legacy flows never create a job row beforehand, and refusing them
    would break publishing.

    The unknown-job branch used to be `SELECT`, then decide — a check-then-act
    race. `/publish` is a sync `def`, so FastAPI runs it in the threadpool and two
    requests really do run in parallel. Measured before the fix: both callers got
    through and the single legacy video was uploaded twice (8 uploads, 2 posts).
    Now the row is claimed by an INSERT whose PRIMARY KEY arbitrates, inside the
    write transaction the UPDATE above already opened. `kind` only labels the row
    that is created for a previously-unknown job (the image flow has no row either).
    """
    with _connect(media_dir) as conn:
        cur = conn.execute(
            "UPDATE jobs SET state='publishing', updated_at=? "
            "WHERE id=? AND state NOT IN ('publishing', 'done')",
            (_utc_now(), job_id),
        )
        if cur.rowcount:
            return True
        # Row exists but is publishing/done: a real duplicate, refuse it.
        if conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            return False
        # Unknown job (legacy/curl flow): claim it by creating the row. The UPDATE
        # above already holds a write lock, so exactly one concurrent caller wins;
        # the loser hits the primary key and gets IntegrityError.
        try:
            conn.execute(
                "INSERT INTO jobs "
                "(id, kind, state, title, payload_json, error, created_at, updated_at) "
                "VALUES (?, ?, 'publishing', NULL, '{}', NULL, ?, ?)",
                (job_id, kind, _utc_now(), _utc_now()),
            )
        except sqlite3.IntegrityError:
            return False
    return True


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


def claim_new_job(
    media_dir: str | Path,
    *,
    kind: str = "video",
    topic: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Yeni iş için üretim hakkını ATOMİK olarak alır; alınamazsa None.

    `/generate` ve `/generate-image` guard'ı (`pending.json` + `has_blocking_job`)
    ile `create_job` arasında `await` var: event loop serbest kalıyor, ikinci
    istek guard'ı geçip ikinci bir üretim başlatıyordu. Ölçüm: iki eşzamanlı
    `/generate` isteği de 200 aldı ve `generate_video` 2 kez çağrıldı.

    Guard'ı tek bir koşullu INSERT'e indiriyoruz: SQLite'ın yazma kilidi
    denetle-ve-yaz'ı atomik yapıyor, ayrı bir kilit defteri gerekmiyor.
    `publishing` durumu da engelliyor — yayın sürerken yeni video üretmek
    aynı anda iki videoyu yayına hazırlamak olur.

    `pending.json` ayrıca kontrol ediliyor: eski/curl ve yalnızca-görsel akışlar
    DB satırı oluşturmadan sadece bu dosyayı yazıyor, o yüzden DB sorgusu tek
    başına onları görmüyor.
    """
    media = Path(media_dir)
    if (media / "pending.json").is_file():
        return None
    job_id = new_job_id(now)
    with _connect(media) as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (id, kind, state, topic, title, payload_json, error, created_at, updated_at)
            SELECT ?, ?, 'generating', ?, NULL, '{}', NULL, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM jobs
                WHERE state IN ('generating', 'awaiting_approval', 'publishing')
            )
            """,
            (job_id, kind, topic, _utc_now(), _utc_now()),
        )
        if cur.rowcount:
            return job_id
    return None


def write_pending_mirror(media_dir: str | Path, payload: dict[str, Any]) -> None:
    """Double-write pending.json so the Telegram/n8n paths keep working.

    `pending.json` is a *public* file: catchup, daily_digest, telegram_bot and the
    `/pending` and `/media` endpoints all read it. A plain `write_text` opens the
    file with O_TRUNC, so the file is empty from that instant until the next
    flush — a concurrent reader sees `{}` or a half payload. Measured on
    Windows: 392 of 682 reads (57%) during 3000 back-to-back writes raised
    JSONDecodeError ("Unterminated string", "Expecting value").

    Consequences were not cosmetic: an empty payload makes
    `read_pending_payload` fall through to the 404 branch of /pending, and
    telegram_bot treats the empty dict as "no pending job" — so a Telegram press
    during generation reports nothing to approve while the real approval is
    silently still armed.

    `write_atomic` writes a sibling temp file and swaps it in with os.replace,
    so readers see either the old or the new payload, never a torn one. Two
    Windows caveats come with the rename: os.replace raises PermissionError
    (WinError 5) while the target is open (*measured* — a plain reader thread is
    enough), so writers and readers share `_pending_lock`; a foreign handle
    (n8n, host tool) is outside that lock and is covered by a bounded retry.
    """
    media = Path(media_dir)
    media.mkdir(parents=True, exist_ok=True)
    with _pending_lock:
        _replace_with_retry(media / "pending.json", payload)


def _replace_with_retry(
    path: Path, payload: Any, *, attempts: int = 10, initial_delay: float = 0.005
) -> None:
    """`write_atomic` with a short retry for handles held outside this process.

    `_pending_lock` serialises our own readers/writers, so the only way this
    still hits WinError 5 is a foreign handle (n8n, a host tool) opening
    pending.json. Retry briefly; a genuinely stuck file raises after the last
    attempt instead of silently falling back to a non-atomic write.
    """
    delay = initial_delay
    for attempt in range(1, attempts + 1):
        try:
            write_atomic(path, payload)
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def _quarantine_corrupt(path: Path) -> None:
    """Move unreadable JSON aside so disk state matches "there is no pending job".

    Anything that can actually be parsed is returned as-is; this runs only when
    the file cannot be read. Leaving it in place is what produced a permanent
    500: every /pending, /media and Telegram read re-parsed the same bad bytes,
    and only a manual delete recovered.
    """
    try:
        data = path.read_bytes()
    except OSError:
        logger.warning("pending.json okunamadi (silinemedi de): %s", path)
        return
    try:
        path.with_suffix(path.suffix + ".corrupt").write_bytes(data)
    except OSError:
        logger.warning("pending.json karantinaya alinamadi: %s", path)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("bozuk pending.json silinemedi: %s", path)
        return
    logger.warning(
        "Bozuk pending.json karantinaya alindi (%s.corrupt, %d bayt); "
        "onay kaybi olabilir",
        path,
        len(data),
    )


def _read_json_tolerant(path: Path) -> dict[str, Any] | None:
    """Read a JSON object; `None` instead of raising when the file is unusable.

    `jsonstore.read_json` is deliberately not reused here: it catches only
    JSONDecodeError (a torn multi-byte write raises UnicodeDecodeError) and it
    degrades to a caller-supplied default instead of quarantining, which for
    pending.json would leave the bad bytes in place and keep the 500 alive.

    Reads take `_pending_lock` so the file is never open while another thread
    calls os.replace (Windows refuses that rename — measured).
    """
    with _pending_lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            logger.warning(
                "pending.json kullanilamaz (%s: %s) — karantinaya aliniyor",
                type(exc).__name__,
                exc,
            )
            _quarantine_corrupt(path)
            return None
    return data if isinstance(data, dict) else None


def read_pending_payload(media_dir: str | Path) -> dict[str, Any] | None:
    """Prefer SQLite awaiting_approval payload; fall back to pending.json."""
    job = get_awaiting_approval(media_dir)
    if job and isinstance(job.get("payload"), dict) and job["payload"]:
        payload = dict(job["payload"])
        payload.setdefault("job_id", job["id"])
        return payload
    pending_path = Path(media_dir) / "pending.json"
    if pending_path.is_file():
        return _read_json_tolerant(pending_path)
    return None


def clear_pending_mirror(media_dir: str | Path, job_id: str | None = None) -> None:
    """Drop the DB row and the pending.json mirror.

    The unlink retries for the same reason `main._unlink_quietly` does: a
    concurrent /cleanup and /publish (or two /cleanup calls) can reach this line
    together and the loser gets PermissionError (WinError 5) on Windows, which
    surfaced as a 500 to that caller. pending.json was left out of that earlier
    fix because it is not an artifact — same defect, different file.
    """
    clear_awaiting(media_dir, job_id)
    with _pending_lock:
        _unlink_with_retry(Path(media_dir, "pending.json"))


def _unlink_with_retry(path: Path, *, attempts: int = 10, initial_delay: float = 0.005) -> None:
    """Delete `path`, tolerating a concurrent delete or an open reader handle."""
    delay = initial_delay
    for attempt in range(1, attempts + 1):
        try:
            path.unlink(missing_ok=True)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(delay)
            delay *= 2


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
    except json.JSONDecodeError:
        data["payload"] = {}
    return data
