from unittest.mock import Mock, patch

from app.publishers.linkedin import upload_to_linkedin


def _token_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"access_token": "li-access"}
    return resp


def _init_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "value": {
            "uploadUrl": "https://upload.example.com/img123",
            "image": "urn:li:digitalmediaAsset:D123",
        }
    }
    return resp


def _put_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


def _post_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.headers = {"x-restli-id": "urn:li:share:789"}
    return resp


@patch("app.publishers.linkedin.session.post")
@patch("app.publishers.linkedin.session.put")
def test_upload_to_linkedin_success(mock_put, mock_post, tmp_path):
    image_path = tmp_path / "post.png"
    image_path.write_bytes(b"FAKEPNG")

    mock_post.side_effect = [_token_response(), _init_response(), _post_response()]
    mock_put.return_value = _put_response()

    result = upload_to_linkedin(
        str(image_path),
        "Bu bir test gönderisi #bilgi",
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
        author_urn="urn:li:person:P1",
    )

    assert result == {
        "platform": "linkedin",
        "status": "success",
        "post_id": "urn:li:share:789",
    }

    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["json"]["initializeUploadRequest"]["owner"] == (
        "urn:li:person:P1"
    )
    assert mock_put.call_args.args[0] == "https://upload.example.com/img123"

    create_call = mock_post.call_args_list[2]
    assert create_call.kwargs["json"]["content"]["media"]["id"] == (
        "urn:li:digitalmediaAsset:D123"
    )
    assert create_call.kwargs["json"]["commentary"] == "Bu bir test gönderisi #bilgi"


@patch("app.publishers.linkedin.session.post")
@patch("app.publishers.linkedin.session.put")
def test_upload_to_linkedin_returns_error_dict_on_failure(mock_put, mock_post, tmp_path):
    image_path = tmp_path / "post.png"
    image_path.write_bytes(b"FAKEPNG")

    mock_post.side_effect = Exception("LinkedIn API down")

    result = upload_to_linkedin(
        str(image_path),
        "metin",
        client_id="c",
        client_secret="s",
        refresh_token="r",
        author_urn="urn:li:person:P1",
    )

    assert result["platform"] == "linkedin"
    assert result["status"] == "error"
    assert "LinkedIn API down" in result["error"]
