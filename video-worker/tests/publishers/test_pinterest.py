from unittest.mock import patch, Mock

from app.publishers.pinterest import upload_to_pinterest


def _resp(json_data=None):
    resp = Mock()
    resp.raise_for_status = Mock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


@patch("app.publishers.pinterest.time.sleep")
@patch("app.publishers.pinterest.session.get")
@patch("app.publishers.pinterest.session.post")
def test_upload_to_pinterest_success(mock_post, mock_get, mock_sleep, tmp_path):
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"VIDEOBYTES")

    mock_post.side_effect = [
        # 1. Token response
        _resp({"access_token": "pin_tok_123"}),
        # 2. Register media response
        _resp({
            "media_id": "med_999",
            "upload_url": "https://pinterest-upload.s3.amazonaws.com",
            "upload_parameters": {"key": "abc"},
        }),
        # 3. S3 upload response
        _resp(),
        # 4. Create pin response
        _resp({"id": "pin_555"}),
    ]
    # Media polling response
    mock_get.return_value = _resp({"status": "succeeded"})

    result = upload_to_pinterest(
        video_path=str(video_file),
        title="Stoic Wealth Rules",
        description="Detailed description with #wealth #luxury",
        client_id="cid",
        client_secret="sec",
        refresh_token="ref",
        board_id="board_123",
    )

    assert result == {
        "platform": "pinterest",
        "status": "success",
        "pin_id": "pin_555",
        "url": "https://www.pinterest.com/pin/pin_555/",
    }
    assert mock_post.call_count == 4
    pin_call = mock_post.call_args_list[3]
    assert pin_call.kwargs["json"]["board_id"] == "board_123"
    assert pin_call.kwargs["json"]["media_source"]["media_id"] == "med_999"


@patch("app.publishers.pinterest.time.sleep")
@patch("app.publishers.pinterest.session.get")
@patch("app.publishers.pinterest.session.post")
def test_upload_to_pinterest_polls_until_succeeded(mock_post, mock_get, mock_sleep, tmp_path):
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"VIDEOBYTES")

    mock_post.side_effect = [
        _resp({"access_token": "pin_tok_123"}),
        _resp({
            "media_id": "med_999",
            "upload_url": "https://s3.amazonaws.com",
            "upload_parameters": {},
        }),
        _resp(),
        _resp({"id": "pin_555"}),
    ]
    mock_get.side_effect = [
        _resp({"status": "processing"}),
        _resp({"status": "succeeded"}),
    ]

    result = upload_to_pinterest(
        video_path=str(video_file),
        title="Title",
        description="Desc",
        client_id="cid",
        client_secret="sec",
        refresh_token="ref",
        board_id="board_123",
    )

    assert result["status"] == "success"
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1


@patch("app.publishers.pinterest.session.get")
@patch("app.publishers.pinterest.session.post")
def test_upload_to_pinterest_fails_on_media_error(mock_post, mock_get, tmp_path):
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"VIDEOBYTES")

    mock_post.side_effect = [
        _resp({"access_token": "pin_tok_123"}),
        _resp({
            "media_id": "med_999",
            "upload_url": "https://s3.amazonaws.com",
            "upload_parameters": {},
        }),
        _resp(),
    ]
    mock_get.return_value = _resp({"status": "failed"})

    result = upload_to_pinterest(
        video_path=str(video_file),
        title="Title",
        description="Desc",
        client_id="cid",
        client_secret="sec",
        refresh_token="ref",
        board_id="board_123",
    )

    assert result["status"] == "error"
    assert "failed processing" in result["error"]


def test_upload_to_pinterest_missing_credentials():
    result = upload_to_pinterest(
        video_path="video.mp4",
        title="Title",
        description="Desc",
        client_id="",
        client_secret="",
        refresh_token="",
        board_id="",
    )
    assert result["status"] == "error"
    assert "missing" in result["error"]
