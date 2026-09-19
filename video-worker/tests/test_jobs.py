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


def test_read_pending_falls_back_to_json(tmp_path):
    (tmp_path / "pending.json").write_text(
        '{"job_id": "legacy", "title": "from-json"}', encoding="utf-8"
    )
    payload = job_store.read_pending_payload(tmp_path)
    assert payload["title"] == "from-json"
