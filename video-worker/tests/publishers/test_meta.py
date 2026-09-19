from unittest.mock import patch, Mock

from app.publishers.meta import upload_to_instagram, upload_to_facebook


def _resp(json_data=None):
    resp = Mock()
    resp.raise_for_status = Mock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


@patch("app.publishers.meta.time.sleep")
@patch(
    "app.publishers.meta.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.meta.session.get")
@patch("app.publishers.meta.session.post")
def test_upload_to_instagram_success(mock_post, mock_get, mock_tunnel, mock_sleep):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "media456"})]
    mock_get.return_value = _resp({"status_code": "FINISHED"})

    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="Why flamingos stand on one leg #facts",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result == {
        "platform": "instagram",
        "status": "success",
        "media_id": "media456",
    }

    create_call = mock_post.call_args_list[0]
    assert (
        create_call.kwargs["data"]["video_url"]
        == "https://abc123.trycloudflare.com/media/job123.mp4"
    )
    assert create_call.kwargs["data"]["media_type"] == "REELS"


@patch("app.publishers.meta.time.sleep")
@patch(
    "app.publishers.meta.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.meta.session.get")
@patch("app.publishers.meta.session.post")
def test_upload_to_instagram_polls_until_finished(
    mock_post, mock_get, mock_tunnel, mock_sleep
):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "media456"})]
    mock_get.side_effect = [
        _resp({"status_code": "IN_PROGRESS"}),
        _resp({"status_code": "FINISHED"}),
    ]

    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="caption",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["status"] == "success"
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()


@patch("app.publishers.meta.get_tunnel_url", side_effect=RuntimeError("no tunnel url"))
def test_upload_to_instagram_returns_error_when_tunnel_unavailable(mock_tunnel):
    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="caption",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["platform"] == "instagram"
    assert result["status"] == "error"
    assert "no tunnel url" in result["error"]


@patch("app.publishers.meta.session.post")
def test_upload_to_facebook_success(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_post.side_effect = [
        _resp({"video_id": "vid789", "upload_url": "https://rupload.facebook.com/xyz"}),
        _resp({}),
        _resp({"success": True}),
    ]

    result = upload_to_facebook(
        str(video_path),
        description="Why flamingos stand on one leg",
        page_id="page123",
        page_access_token="page-tok",
    )

    assert result == {
        "platform": "facebook",
        "status": "success",
        "video_id": "vid789",
    }

    upload_call = mock_post.call_args_list[1]
    assert upload_call.kwargs["headers"]["Authorization"] == "OAuth page-tok"
    finish_call = mock_post.call_args_list[2]
    assert finish_call.kwargs["data"]["video_id"] == "vid789"
    assert finish_call.kwargs["data"]["upload_phase"] == "finish"


@patch("app.publishers.meta.session.post")
def test_upload_to_facebook_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    mock_post.side_effect = Exception("start phase failed")

    result = upload_to_facebook(
        str(video_path), description="d", page_id="page123", page_access_token="tok"
    )

    assert result["platform"] == "facebook"
    assert result["status"] == "error"
    assert "start phase failed" in result["error"]
