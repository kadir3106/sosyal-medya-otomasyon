import json
from datetime import datetime, timezone
from unittest.mock import patch

from app.daily_digest import (
    DIGEST_MARKER_FILENAME,
    _local_today_start_utc,
    build_daily_digest,
    maybe_send_digest,
)


def _write_log(media_dir, entries):
    log_path = media_dir / "published_log.json"
    log_path.write_text(json.dumps(entries), encoding="utf-8")


def _sample_entry(title="Test Video", published_at="2026-09-06T18:05:00+00:00", kind="video"):
    return {
        "published_at": published_at,
        "title": title,
        "kind": kind,
        "platforms": {
            "youtube": {"platform": "youtube", "status": "success"},
            "tiktok": {"platform": "tiktok", "status": "error", "error": "403 denied"},
        },
    }


def test_local_today_start_utc_converts_istanbul_midnight():
    # 2026-09-06 22:30 Istanbul = 2026-09-06 19:30 UTC (yaz saati UTC+3).
    now = datetime(2026, 9, 6, 19, 30, tzinfo=timezone.utc)
    start = _local_today_start_utc(now)
    # Istanbul'da 2026-09-06 00:00 == UTC 2026-09-05 21:00 (yaz saati UTC+3).
    assert start == "2026-09-05T21:00:00+00:00"


def test_build_daily_digest_reports_empty_day(tmp_path):
    message = build_daily_digest(
        str(tmp_path),
        now=datetime(2026, 9, 6, 21, 0, tzinfo=timezone.utc),
    )
    assert "Bugün yeni bir içerik yayınlanmadı." in message
    assert "Bekleyen onay yok." in message


def test_build_daily_digest_lists_only_today_entries(tmp_path):
    # now = 2026-09-06 21:00 UTC == Istanbul'da 2026-09-07 00:00. Yani "bugün"
    # Istanbul'da 7 Eylül; onun UTC başlangıcı 2026-09-06T21:00+00:00.
    _write_log(
        tmp_path,
        [
            _sample_entry(title="Bugünün videosu", published_at="2026-09-06T21:30:00+00:00"),
            _sample_entry(title="Dünün videosu", published_at="2026-09-06T18:05:00+00:00"),
        ],
    )
    message = build_daily_digest(
        str(tmp_path),
        now=datetime(2026, 9, 6, 21, 0, tzinfo=timezone.utc),
    )
    assert "1 içerik yayınlandı" in message
    assert "Bugünün videosu" in message
    assert "Dünün videosu" not in message
    assert "✅ youtube" in message
    assert "❌ tiktok: 403 denied" in message


def test_build_daily_digest_mentions_pending(tmp_path):
    (tmp_path / "pending.json").write_text(
        json.dumps({"title": "Onay bekleyen", "kind": "video", "video_filename": "x.mp4"}),
        encoding="utf-8",
    )
    message = build_daily_digest(
        str(tmp_path),
        now=datetime(2026, 9, 6, 21, 0, tzinfo=timezone.utc),
    )
    assert "Onay bekleyen" in message


def test_maybe_send_digest_skips_before_hour(tmp_path):
    marker = str(tmp_path / DIGEST_MARKER_FILENAME)
    with patch("app.daily_digest.send_message") as mock_send:
        sent = maybe_send_digest(
            "TOKEN", "123", str(tmp_path), digest_hour=21, marker_path=marker,
            now=datetime(2026, 9, 6, 20, 59),
        )
    assert sent is False
    mock_send.assert_not_called()


def test_maybe_send_digest_sends_once_per_day(tmp_path):
    marker = str(tmp_path / DIGEST_MARKER_FILENAME)
    now = datetime(2026, 9, 6, 21, 30)
    with patch("app.daily_digest.send_message") as mock_send:
        sent = maybe_send_digest(
            "TOKEN", "123", str(tmp_path), digest_hour=21, marker_path=marker, now=now
        )
    assert sent is True
    mock_send.assert_called_once()

    # Aynı gün ikinci deneme — marker var, tekrar gönderme.
    with patch("app.daily_digest.send_message") as mock_send:
        sent = maybe_send_digest(
            "TOKEN", "123", str(tmp_path), digest_hour=21, marker_path=marker, now=now
        )
    assert sent is False
    mock_send.assert_not_called()


def test_maybe_send_digest_uses_custom_send_fn(tmp_path):
    marker = str(tmp_path / DIGEST_MARKER_FILENAME)
    captured = {}

    def fake_send(token, chat_id, text, **kwargs):
        captured["token"] = token
        captured["text"] = text

    sent = maybe_send_digest(
        "TOKEN", "123", str(tmp_path), digest_hour=21, marker_path=marker,
        now=datetime(2026, 9, 6, 21, 30), send_fn=fake_send,
    )
    assert sent is True
    assert captured["token"] == "TOKEN"
    assert "Günlük Özet" in captured["text"]
