import json
from unittest.mock import patch

from app.errors import AllPlatformsFailedError
from app.telegram_bot import _load_offset, _save_offset, handle_callback


def test_offset_round_trip(tmp_path):
    offset_path = str(tmp_path / "offset.json")
    assert _load_offset(offset_path) == 0
    _save_offset(offset_path, 42)
    assert _load_offset(offset_path) == 42


def test_handle_callback_approve_sends_summary(tmp_path):
    (tmp_path / "pending.json").write_text(
        json.dumps({"kind": "video", "title": "T", "video_filename": "job1.mp4"}),
        encoding="utf-8",
    )

    def publish_fn(payload):
        assert payload["title"] == "T"
        return {
            "results": [
                {"platform": "youtube", "status": "success"},
                {"platform": "tiktok", "status": "error", "error": "boom"},
            ]
        }

    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback("approve", str(tmp_path), "TOKEN", "123", publish_fn, lambda f: None)

    text = mock_send.call_args.args[2]
    assert "✅ youtube" in text
    assert "❌ tiktok: boom" in text


def test_handle_callback_approve_no_pending_job(tmp_path):
    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback("approve", str(tmp_path), "TOKEN", "123", lambda p: {}, lambda f: None)

    assert "Bekleyen iş yok" in mock_send.call_args.args[2]


def test_handle_callback_reject_calls_cleanup_and_notifies(tmp_path):
    (tmp_path / "pending.json").write_text(
        json.dumps({"video_filename": "job2.mp4"}), encoding="utf-8"
    )
    cleanup_calls = []

    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback(
            "reject", str(tmp_path), "TOKEN", "123", lambda p: {}, cleanup_calls.append
        )

    assert cleanup_calls == ["job2.mp4"]
    assert "İptal edildi" in mock_send.call_args.args[2]


def test_handle_callback_approve_all_failed_sends_retry_button(tmp_path):
    (tmp_path / "pending.json").write_text(
        json.dumps({"title": "T", "video_filename": "job3.mp4"}), encoding="utf-8"
    )

    def publish_fn(payload):
        raise AllPlatformsFailedError(
            "job3", [{"platform": "youtube", "status": "error", "error": "x"}]
        )

    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback("approve", str(tmp_path), "TOKEN", "123", publish_fn, lambda f: None)

    kwargs = mock_send.call_args.kwargs
    assert kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "retry:job3"


def test_handle_callback_retry_reads_sidecar_and_republishes(tmp_path):
    failed_dir = tmp_path / "failed"
    failed_dir.mkdir()
    sidecar = failed_dir / "job4.json"
    sidecar.write_text(
        json.dumps({"title": "T", "video_path": str(failed_dir / "job4.mp4")}),
        encoding="utf-8",
    )
    seen = {}

    def publish_fn(payload):
        seen["payload"] = payload
        return {"results": [{"platform": "youtube", "status": "success"}]}

    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback("retry:job4", str(tmp_path), "TOKEN", "123", publish_fn, lambda f: None)

    assert seen["payload"]["title"] == "T"
    assert not sidecar.exists()
    assert "✅ youtube" in mock_send.call_args.args[2]


def test_handle_callback_retry_missing_sidecar(tmp_path):
    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback(
            "retry:missing", str(tmp_path), "TOKEN", "123", lambda p: {}, lambda f: None
        )

    assert "artık bulunamadı" in mock_send.call_args.args[2]


def test_handle_callback_pitch_generates_and_sends_preview(tmp_path):
    pitches = [
        {"id": 1, "title": "Komedi Başlık", "topic": "Komedi Konu", "category_label": "😂 Komedi"},
    ]
    (tmp_path / "pending_pitches.json").write_text(json.dumps(pitches), encoding="utf-8")

    video_file = tmp_path / "preview.mp4"
    video_file.write_bytes(b"VIDEO")

    def fake_generate(topic):
        assert topic == "Komedi Konu"
        return {
            "title": "Komedi Başlık",
            "description": "Açıklama #komedi",
            "video_path": str(video_file),
        }

    with patch("app.telegram_bot.send_video") as mock_send_video, patch("app.telegram_bot.send_message") as mock_send_msg:
        handle_callback(
            "pitch:1",
            str(tmp_path),
            "TOKEN",
            "123",
            publish_fn=lambda p: {},
            cleanup_fn=lambda f: None,
            generate_fn=fake_generate,
        )

    assert mock_send_video.called
    kwargs = mock_send_video.call_args.kwargs
    assert "onaylıyor musun" in kwargs["caption"].lower()
    assert kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve"


def test_handle_callback_approve_reads_job_store_without_mirror(tmp_path):
    """Approve must work from SQLite awaiting_approval even if pending.json is gone."""
    from app import jobs as job_store

    payload = {
        "kind": "video",
        "title": "SQLite only",
        "video_filename": "job-sqlite.mp4",
    }
    job_store.create_job(
        tmp_path,
        "job-sqlite",
        kind="video",
        state="awaiting_approval",
        title="SQLite only",
        payload=payload,
    )

    def publish_fn(body):
        assert body["title"] == "SQLite only"
        return {"results": [{"platform": "youtube", "status": "success"}]}

    with patch("app.telegram_bot.send_message") as mock_send:
        handle_callback(
            "approve", str(tmp_path), "TOKEN", "123", publish_fn, lambda f: None
        )

    assert "✅ youtube" in mock_send.call_args.args[2]
