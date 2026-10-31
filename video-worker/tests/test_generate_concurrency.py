"""Regression: the /generate guard and the job row must be one atomic step.

The endpoint awaits `generate_video`, which hands the work to a thread and frees
the event loop. With a separate check-then-create, two concurrent requests both
passed the guard: measured 40/40 topics ok but `codes=[200, 200]` and the
pipeline invoked twice. `job_id` also used second resolution only, so both
requests got the same id, wrote to the same work_dir, and the jobs table kept a
single row.
"""
from __future__ import annotations

import asyncio
import sqlite3

import httpx
import pytest

from app import jobs as job_store
from app import main as main_mod


async def _post_twice(path: str, media_dir) -> tuple[list[int], int]:
    """Two genuinely concurrent POSTs against a fresh media dir."""
    calls = {"n": 0}

    async def fake_generate_video(job_id, topic=None):
        calls["n"] += 1
        await asyncio.sleep(0)  # yield like asyncio.to_thread does
        return {"job_id": job_id, "video_filename": f"{job_id}.mp4"}

    main_mod.config.MEDIA_DIR = str(media_dir)
    main_mod.generate_video = fake_generate_video

    transport = httpx.ASGITransport(app=main_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        responses = await asyncio.gather(
            client.post(path), client.post(path), return_exceptions=True
        )
    codes = [getattr(r, "status_code", -1) for r in responses]
    return codes, calls["n"]


def test_concurrent_generate_starts_pipeline_once(tmp_path):
    codes, invocations = asyncio.run(_post_twice("/generate", tmp_path))

    assert sorted(codes) == [200, 409], f"both requests ran: {codes}"
    assert invocations == 1, f"pipeline ran {invocations} times"


def test_generate_returns_409_while_generation_in_progress(tmp_path):
    job_store.claim_new_job(tmp_path, kind="video")
    main_mod.config.MEDIA_DIR = str(tmp_path)

    transport = httpx.ASGITransport(app=main_mod.app)

    async def call():
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            return await client.post("/generate")

    response = asyncio.run(call())

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


@pytest.mark.parametrize("path", ["/generate", "/generate-image"])
def test_pending_json_without_db_row_still_blocks(tmp_path, path):
    """Legacy/curl flow writes only pending.json — the guard must still fire."""
    (tmp_path / "pending.json").write_text("{}", encoding="utf-8")

    assert job_store.claim_new_job(tmp_path) is None


def test_claim_new_job_is_exclusive(tmp_path):
    first = job_store.claim_new_job(tmp_path, kind="video")
    assert first is not None
    assert len(first) > 15  # timestamp + random suffix
    assert job_store.claim_new_job(tmp_path, kind="video") is None


def test_claim_new_job_allowed_again_after_job_fails(tmp_path):
    """A failed generation must not block the channel forever."""
    job_id = job_store.claim_new_job(tmp_path, kind="video")
    job_store.mark_failed(tmp_path, job_id, "pexels_timeout")

    assert job_store.claim_new_job(tmp_path, kind="video") is not None


def test_claim_new_job_allowed_again_after_publish_clears(tmp_path):
    job_id = job_store.claim_new_job(tmp_path, kind="video")
    job_store.update_job(tmp_path, job_id, state="awaiting_approval")
    job_store.write_pending_mirror(tmp_path, {"job_id": job_id})
    assert job_store.claim_new_job(tmp_path, kind="video") is None

    job_store.clear_pending_mirror(tmp_path, job_id)

    assert job_store.claim_new_job(tmp_path, kind="video") is not None


def test_new_job_id_does_not_collide_within_one_second():
    from datetime import datetime, timezone

    frozen = datetime(2026, 10, 31, 7, 5, 12, tzinfo=timezone.utc)
    ids = [job_store.new_job_id(frozen) for _ in range(50)]

    assert len(set(ids)) == 50, "same-second job ids collided"
    assert all(i.startswith("20261031-070512-") for i in ids)


def test_concurrent_claims_only_one_wins(tmp_path):
    import threading

    won: list[str] = []
    guard = threading.Lock()

    def racer():
        got = job_store.claim_new_job(tmp_path, kind="video")
        if got:
            with guard:
                won.append(got)

    threads = [threading.Thread(target=racer) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(won) == 1, f"{len(won)} claims won, expected exactly 1"
    conn = sqlite3.connect(str(tmp_path / "jobs.db"))
    rows = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    assert rows == 1
