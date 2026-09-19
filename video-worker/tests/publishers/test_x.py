from unittest.mock import Mock, patch

from app.publishers.x import upload_to_x, upload_video_to_x


def _token_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"access_token": "x-access"}
    return resp


def _media_response(media_id="m123"):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"data": {"id": media_id}}
    return resp


def _tweet_response(tweet_id="t456"):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"data": {"id": tweet_id}}
    return resp


@patch("app.publishers.x.session.post")
def test_upload_to_x_image_success(mock_post, tmp_path):
    image_path = tmp_path / "post.png"
    image_path.write_bytes(b"FAKEPNG")

    mock_post.side_effect = [
        _token_response(),
        _media_response("m123"),
        _tweet_response("t456"),
    ]

    result = upload_to_x(
        str(image_path),
        "Görsel post metni",
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result == {
        "platform": "x",
        "status": "success",
        "tweet_id": "t456",
        "url": "https://x.com/i/web/status/t456",
    }

    token_call = mock_post.call_args_list[0]
    assert token_call.kwargs["auth"] == ("cid", "csecret")
    assert token_call.kwargs["data"]["refresh_token"] == "rtoken"

    media_call = mock_post.call_args_list[1]
    assert media_call.kwargs["files"] is not None
    assert media_call.kwargs["data"]["media_category"] == "tweet_image"

    tweet_call = mock_post.call_args_list[2]
    assert tweet_call.kwargs["json"]["text"] == "Görsel post metni"
    assert tweet_call.kwargs["json"]["media"]["media_ids"] == ["m123"]


@patch("app.publishers.x.time.sleep")
@patch("app.publishers.x.session.get")
@patch("app.publishers.x.session.post")
def test_upload_to_x_video_chunked_success(mock_post, mock_get, mock_sleep, tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"FAKEVIDEODATA")

    mock_init = Mock()
    mock_init.raise_for_status = Mock()
    mock_init.json.return_value = {"media_id_string": "vid_chunk_1"}

    mock_append = Mock()
    mock_append.raise_for_status = Mock()

    mock_fin = Mock()
    mock_fin.raise_for_status = Mock()
    mock_fin.json.return_value = {
        "media_id_string": "vid_chunk_1",
        "processing_info": {"state": "pending", "check_after_secs": 1},
    }

    mock_post.side_effect = [
        _token_response(),
        mock_init,
        mock_append,
        mock_fin,
        _tweet_response("tweet_vid_1"),
    ]

    mock_status = Mock()
    mock_status.raise_for_status = Mock()
    mock_status.json.return_value = {"processing_info": {"state": "succeeded"}}
    mock_get.return_value = mock_status

    # Test auto-delegation when file ends with .mp4
    result = upload_to_x(
        str(video_path),
        "Dark Wealth rules #Shorts",
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result == {
        "platform": "x",
        "status": "success",
        "tweet_id": "tweet_vid_1",
        "url": "https://x.com/i/web/status/tweet_vid_1",
    }
    assert mock_post.call_count == 5
    assert mock_get.call_count == 1

    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["data"]["command"] == "INIT"
    assert init_call.kwargs["data"]["media_category"] == "tweet_video"

    tweet_call = mock_post.call_args_list[4]
    assert tweet_call.kwargs["json"]["media"]["media_ids"] == ["vid_chunk_1"]


@patch("app.publishers.x.session.post")
def test_upload_to_x_returns_error_dict_on_failure(mock_post, tmp_path):
    image_path = tmp_path / "post.png"
    image_path.write_bytes(b"FAKEPNG")

    mock_post.side_effect = Exception("X API down")

    result = upload_to_x(
        str(image_path), "metin", client_id="c", client_secret="s", refresh_token="r"
    )

    assert result["platform"] == "x"
    assert result["status"] == "error"
    assert "X API down" in result["error"]
