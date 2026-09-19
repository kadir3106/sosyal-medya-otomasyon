import json
from datetime import datetime, timezone
from unittest.mock import patch, Mock

import requests

from app.analytics import build_weekly_report


def _resp(json_data):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data
    return resp


def test_build_weekly_report_returns_message_when_no_entries(tmp_path):
    log_path = tmp_path / "log.json"

    report = build_weekly_report(
        str(log_path),
        youtube_creds={"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        meta_creds={"page_access_token": "t"},
    )

    assert report == "Son 7 günde yayınlanan video yok."


@patch("app.analytics.session.get")
@patch("app.analytics.get_youtube_access_token", return_value="yt-access-tok")
def test_build_weekly_report_includes_platform_stats(mock_token, mock_get, tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps(
            [
                {
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "title": "Why Flamingos Stand on One Leg",
                    "platforms": {
                        "youtube": {
                            "platform": "youtube", "status": "success", "video_id": "yt1"
                        },
                        "instagram": {
                            "platform": "instagram", "status": "success", "media_id": "ig1"
                        },
                        "facebook": {
                            "platform": "facebook", "status": "success", "video_id": "fb1"
                        },
                        "tiktok": {
                            "platform": "tiktok", "status": "success",
                            "publish_id": "tt1", "privacy_level": "SELF_ONLY",
                        },
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    mock_get.side_effect = [
        _resp(
            {"items": [{"statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "5"}}]}
        ),
        _resp({"data": [{"name": "plays", "values": [{"value": 200}]}]}),
        _resp({"id": "fb1", "views": 75}),
    ]

    report = build_weekly_report(
        str(log_path),
        youtube_creds={"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        meta_creds={"page_access_token": "t"},
    )

    assert "Why Flamingos Stand on One Leg" in report
    assert "1000 views" in report
    assert "200 plays" in report
    assert "TikTok" in report


@patch("app.analytics.session.get")
@patch("app.analytics.get_youtube_access_token", return_value="yt-access-tok")
def test_build_weekly_report_isolates_one_platform_failure(
    mock_token, mock_get, tmp_path
):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps(
            [
                {
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "title": "Why Flamingos Stand on One Leg",
                    "platforms": {
                        "youtube": {
                            "platform": "youtube", "status": "success", "video_id": "yt1"
                        },
                        "instagram": {
                            "platform": "instagram", "status": "success", "media_id": "ig1"
                        },
                        "facebook": {
                            "platform": "facebook", "status": "success", "video_id": "fb1"
                        },
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    def get_side_effect(url, **kwargs):
        if "youtube" in url or "googleapis" in url:
            raise requests.exceptions.HTTPError("rate limited")
        if "insights" in url:
            return _resp({"data": [{"name": "plays", "values": [{"value": 200}]}]})
        return _resp({"id": "fb1", "views": 75})

    mock_get.side_effect = get_side_effect

    report = build_weekly_report(
        str(log_path),
        youtube_creds={"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        meta_creds={"page_access_token": "t"},
    )

    assert "Why Flamingos Stand on One Leg" in report
    assert "YouTube: veriler alınamadı" in report
    assert "200 plays" in report
    assert "75" in report
