from unittest.mock import patch, Mock

from app.publishers.youtube import upload_to_youtube


def _token_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"access_token": "access-tok"}
    return resp


def _init_response(location):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.headers = {"Location": location}
    return resp


def _upload_response(video_id):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"id": video_id}
    return resp


@patch("app.publishers.youtube.session.put")
@patch("app.publishers.youtube.session.post")
def test_upload_to_youtube_success(mock_post, mock_put, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_post.side_effect = [
        _token_response(),
        _init_response("https://upload.example.com/resumable/xyz"),
    ]
    mock_put.return_value = _upload_response("abc123")

    result = upload_to_youtube(
        str(video_path),
        title="Why Flamingos Stand on One Leg",
        description="desc",
        tags=["flamingo"],
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result == {
        "platform": "youtube",
        "status": "success",
        "video_id": "abc123",
        "url": "https://youtube.com/shorts/abc123",
    }

    token_call = mock_post.call_args_list[0]
    assert token_call.kwargs["data"]["refresh_token"] == "rtoken"
    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["headers"]["Authorization"] == "Bearer access-tok"
    assert init_call.kwargs["json"]["status"]["privacyStatus"] == "unlisted"


@patch("app.publishers.youtube.session.put")
@patch("app.publishers.youtube.session.post")
def test_upload_to_youtube_sets_thumbnail_when_path_given(mock_post, mock_put, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    thumbnail_path = tmp_path / "thumb.png"
    thumbnail_path.write_bytes(b"FAKEPNG")

    thumb_response = Mock()
    thumb_response.raise_for_status = Mock()
    mock_post.side_effect = [
        _token_response(),
        _init_response("https://upload.example.com/resumable/xyz"),
        thumb_response,
    ]
    mock_put.return_value = _upload_response("abc123")

    result = upload_to_youtube(
        str(video_path),
        title="t", description="d", tags=[],
        client_id="cid", client_secret="csecret", refresh_token="rtoken",
        thumbnail_path=str(thumbnail_path),
    )

    assert result["thumbnail"] == {"status": "success"}
    thumb_call = mock_post.call_args_list[2]
    assert thumb_call.kwargs["params"]["videoId"] == "abc123"
    assert thumb_call.kwargs["headers"]["Authorization"] == "Bearer access-tok"


@patch("app.publishers.youtube.session.put")
@patch("app.publishers.youtube.session.post")
def test_upload_to_youtube_succeeds_even_if_thumbnail_fails(mock_post, mock_put, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    thumbnail_path = tmp_path / "thumb.png"
    thumbnail_path.write_bytes(b"FAKEPNG")

    mock_post.side_effect = [
        _token_response(),
        _init_response("https://upload.example.com/resumable/xyz"),
        Exception("no phone verification"),
    ]
    mock_put.return_value = _upload_response("abc123")

    result = upload_to_youtube(
        str(video_path),
        title="t", description="d", tags=[],
        client_id="cid", client_secret="csecret", refresh_token="rtoken",
        thumbnail_path=str(thumbnail_path),
    )

    assert result["status"] == "success"
    assert result["video_id"] == "abc123"
    assert result["thumbnail"]["status"] == "error"
    assert "no phone verification" in result["thumbnail"]["error"]


@patch("app.publishers.youtube.session.post")
def test_upload_to_youtube_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    mock_post.side_effect = Exception("token refresh failed")

    result = upload_to_youtube(
        str(video_path),
        title="t",
        description="d",
        tags=[],
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result["platform"] == "youtube"
    assert result["status"] == "error"
    assert "token refresh failed" in result["error"]
