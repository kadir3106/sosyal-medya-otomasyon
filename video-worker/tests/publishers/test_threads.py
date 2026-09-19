from unittest.mock import patch, Mock

from app.publishers.threads import upload_to_threads


def _resp(json_data=None):
    resp = Mock()
    resp.raise_for_status = Mock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


@patch("app.publishers.threads.time.sleep")
@patch(
    "app.publishers.threads.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.threads.session.get")
@patch("app.publishers.threads.session.post")
def test_upload_to_threads_success(mock_post, mock_get, mock_tunnel, mock_sleep):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "post789"})]
    mock_get.return_value = _resp({"status": "FINISHED"})

    result = upload_to_threads(
        video_filename="job123.mp4",
        caption="Why luxury watches retain value #DarkWealth",
        threads_user_id="th_user_1",
        access_token="th_token",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result == {
        "platform": "threads",
        "status": "success",
        "post_id": "post789",
        "url": "https://www.threads.net/post/post789",
    }

    create_call = mock_post.call_args_list[0]
    assert (
        create_call.kwargs["data"]["video_url"]
        == "https://abc123.trycloudflare.com/media/job123.mp4"
    )
    assert create_call.kwargs["data"]["media_type"] == "VIDEO"


@patch("app.publishers.threads.time.sleep")
@patch(
    "app.publishers.threads.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.threads.session.get")
@patch("app.publishers.threads.session.post")
def test_upload_to_threads_polls_until_finished(
    mock_post, mock_get, mock_tunnel, mock_sleep
):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "post789"})]
    mock_get.side_effect = [
        _resp({"status": "IN_PROGRESS"}),
        _resp({"status": "FINISHED"}),
    ]

    result = upload_to_threads(
        video_filename="job123.mp4",
        caption="test",
        threads_user_id="th_user_1",
        access_token="th_token",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["status"] == "success"
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1


@patch("app.publishers.threads.time.sleep")
@patch(
    "app.publishers.threads.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.threads.session.get")
@patch("app.publishers.threads.session.post")
def test_upload_to_threads_handles_container_error(
    mock_post, mock_get, mock_tunnel, mock_sleep
):
    mock_post.return_value = _resp({"id": "creation123"})
    mock_get.return_value = _resp({"status": "ERROR", "error_message": "Invalid aspect ratio"})

    result = upload_to_threads(
        video_filename="job123.mp4",
        caption="test",
        threads_user_id="th_user_1",
        access_token="th_token",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["status"] == "error"
    assert "Invalid aspect ratio" in result["error"]


def test_upload_to_threads_missing_credentials():
    result = upload_to_threads(
        video_filename="job123.mp4",
        caption="test",
        threads_user_id="",
        access_token="",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )
    assert result["status"] == "error"
    assert "missing" in result["error"]
