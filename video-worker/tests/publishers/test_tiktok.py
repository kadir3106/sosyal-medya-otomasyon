import json
from unittest.mock import patch, Mock

from app.publishers.tiktok import upload_to_tiktok


def _refresh_response(access_token, new_refresh_token):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": 86400,
    }
    return resp


def _init_response(publish_id, upload_url):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "data": {"publish_id": publish_id, "upload_url": upload_url}
    }
    return resp


def _ok_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


@patch("app.publishers.tiktok.requests.put")
@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_success_refreshes_and_rotates_token(
    mock_post, mock_put, tmp_path
):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )

    mock_post.side_effect = [
        _refresh_response("access-tok", "new-refresh"),
        _init_response("pub123", "https://upload.tiktokapis.com/xyz"),
    ]
    mock_put.return_value = _ok_response()

    result = upload_to_tiktok(
        str(video_path),
        title="Why Flamingos Stand on One Leg",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=False,
    )

    assert result == {
        "platform": "tiktok",
        "status": "success",
        "publish_id": "pub123",
        "privacy_level": "SELF_ONLY",
    }

    stored = json.loads(token_path.read_text(encoding="utf-8"))
    assert stored["refresh_token"] == "new-refresh"

    refresh_call = mock_post.call_args_list[0]
    assert refresh_call.kwargs["data"]["refresh_token"] == "old-refresh"
    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["json"]["post_info"]["privacy_level"] == "SELF_ONLY"


@patch("app.publishers.tiktok.requests.put")
@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_uses_public_privacy_when_audited(
    mock_post, mock_put, tmp_path
):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )

    mock_post.side_effect = [
        _refresh_response("access-tok", "new-refresh"),
        _init_response("pub456", "https://upload.tiktokapis.com/abc"),
    ]
    mock_put.return_value = _ok_response()

    result = upload_to_tiktok(
        str(video_path),
        title="t",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=True,
    )

    assert result["privacy_level"] == "PUBLIC_TO_EVERYONE"


@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )
    mock_post.side_effect = Exception("refresh failed")

    result = upload_to_tiktok(
        str(video_path),
        title="t",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=False,
    )

    assert result["platform"] == "tiktok"
    assert result["status"] == "error"
    assert "refresh failed" in result["error"]
