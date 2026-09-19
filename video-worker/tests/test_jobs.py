from pathlib import Path

from app import jobs as job_store


def test_job_lifecycle_awaiting_and_pending_mirror(tmp_path):
    payload = {
        "job_id": "job1",
        "video_filename": "job1.mp4",
        "title": "Hello",
        "pinned_comment": "debate?",
    }
    job_store.create_job(tmp_path, "job1", kind="video", state="generating", topic="t")
    job_store.update_job(
        tmp_path,
        "job1",
        state="awaiting_approval",
        title="Hello",
        payload=payload,
        error="",
    )
    job_store.write_pending_mirror(tmp_path, payload)

    assert job_store.has_blocking_job(tmp_path) is True
    awaiting = job_store.get_awaiting_approval(tmp_path)
    assert awaiting is not None
    assert awaiting["id"] == "job1"
    assert awaiting["payload"]["title"] == "Hello"

    mirrored = job_store.read_pending_payload(tmp_path)
    assert mirrored["video_filename"] == "job1.mp4"
    assert (tmp_path / "pending.json").is_file()

    job_store.clear_pending_mirror(tmp_path, "job1")
    assert not (tmp_path / "pending.json").exists()
    assert job_store.get_awaiting_approval(tmp_path) is None
    done = job_store.get_job(tmp_path, "job1")
    assert done["state"] == "done"


def test_clear_pending_mirror_unblocks_publishing_state(tmp_path):
    """Regression: successful publish sets publishing; clear must move it to done."""
    payload = {"job_id": "pub1", "video_filename": "pub1.mp4", "title": "T"}
    job_store.create_job(tmp_path, "pub1", kind="video", state="awaiting_approval", payload=payload)
    job_store.write_pending_mirror(tmp_path, payload)
    job_store.update_job(tmp_path, "pub1", state="publishing", error="")

    assert job_store.has_blocking_job(tmp_path) is True
    job_store.mark_done(tmp_path, "pub1")
    job_store.clear_pending_mirror(tmp_path, "pub1")

    assert job_store.has_blocking_job(tmp_path) is False
    assert job_store.get_job(tmp_path, "pub1")["state"] == "done"
    assert not (tmp_path / "pending.json").exists()


def test_clear_awaiting_covers_publishing_without_prior_mark_done(tmp_path):
    job_store.create_job(tmp_path, "pub2", kind="video", state="publishing")
    assert job_store.has_blocking_job(tmp_path) is True
    job_store.clear_awaiting(tmp_path, "pub2")
    assert job_store.has_blocking_job(tmp_path) is False
    assert job_store.get_job(tmp_path, "pub2")["state"] == "done"


def test_read_pending_falls_back_to_json(tmp_path):
    (tmp_path / "pending.json").write_text(
        '{"job_id": "legacy", "title": "from-json"}', encoding="utf-8"
    )
    payload = job_store.read_pending_payload(tmp_path)
    assert payload["title"] == "from-json"
