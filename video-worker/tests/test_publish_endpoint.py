import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
@patch("app.main.upload_to_x")
@patch("app.main.upload_to_linkedin")
def test_publish_image_calls_x_and_linkedin_and_deletes_file(
    mock_li, mock_x, mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    image_path = tmp_path / "job789.png"
    image_path.write_bytes(b"FAKEPNG")

    mock_x.return_value = {"platform": "x", "status": "success", "tweet_id": "t1"}
    mock_li.return_value = {
        "platform": "linkedin", "status": "success", "post_id": "p1"
    }

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "kind": "image",
                "image_path": str(image_path),
                "image_filename": "job789.png",
                "caption": "Bal hiç bozulmaz #bilgi",
            },
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert {r["platform"] for r in results} == {"x", "linkedin"}
    assert not image_path.exists()

    assert mock_x.call_args.args[1] == "Bal hiç bozulmaz #bilgi"
    assert mock_li.call_args.args[1] == "Bal hiç bozulmaz #bilgi"
    assert not mock_yt.called
    assert not mock_tt.called
    assert not mock_ig.called
    assert not mock_fb.called


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
@patch("app.main.upload_to_x")
@patch("app.main.upload_to_linkedin")
def test_publish_calls_all_four_publishers_and_deletes_file(
    mock_li, mock_x, mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "success", "video_id": "y1", "url": "u"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "t1",
        "privacy_level": "SELF_ONLY",
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "i1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "f1"
    }

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job123.mp4",
                "title": "Why Flamingos Stand on One Leg",
                "description": "desc",
                "tags": ["flamingo"],
            },
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 4
    assert {r["platform"] for r in results} == {
        "youtube", "tiktok", "instagram", "facebook"
    }
    assert not video_path.exists()

    assert mock_yt.call_args.kwargs["title"] == "Why Flamingos Stand on One Leg"
    assert mock_tt.call_args.kwargs["title"] == "Why Flamingos Stand on One Leg"
    assert mock_ig.call_args.kwargs["caption"] == "desc"
    assert mock_fb.call_args.kwargs["description"] == "desc"


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
@patch("app.main.upload_to_x")
@patch("app.main.upload_to_linkedin")
def test_publish_passes_thumbnail_to_youtube_and_deletes_it_on_success(
    mock_li, mock_x, mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job321.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    thumbnail_path = tmp_path / "job321_thumb.png"
    thumbnail_path.write_bytes(b"FAKEPNG")

    mock_yt.return_value = {
        "platform": "youtube", "status": "success", "video_id": "y1", "url": "u"
    }
    mock_tt.return_value = {"platform": "tiktok", "status": "error", "error": "x"}
    mock_ig.return_value = {"platform": "instagram", "status": "error", "error": "x"}
    mock_fb.return_value = {"platform": "facebook", "status": "error", "error": "x"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job321.mp4",
                "thumbnail_path": str(thumbnail_path),
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    assert response.status_code == 200
    assert mock_yt.call_args.kwargs["thumbnail_path"] == str(thumbnail_path)
    assert not video_path.exists()
    assert not thumbnail_path.exists()
    assert not mock_x.called
    assert not mock_li.called


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_continues_when_one_platform_fails(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "error", "error": "quota exceeded"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "t1",
        "privacy_level": "SELF_ONLY",
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "i1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "f1"
    }

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job123.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    results = response.json()["results"]
    assert len(results) == 4
    youtube_result = next(r for r in results if r["platform"] == "youtube")
    assert youtube_result["status"] == "error"


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_returns_502_and_preserves_file_when_all_platforms_fail(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job999.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text("{}", encoding="utf-8")

    mock_yt.return_value = {"platform": "youtube", "status": "error", "error": "quota"}
    mock_tt.return_value = {"platform": "tiktok", "status": "error", "error": "quota"}
    mock_ig.return_value = {"platform": "instagram", "status": "error", "error": "quota"}
    mock_fb.return_value = {"platform": "facebook", "status": "error", "error": "quota"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job999.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    assert response.status_code == 502
    assert not video_path.exists()
    assert not pending_path.exists()

    failed_video = tmp_path / "failed" / "job999.mp4"
    failed_sidecar = tmp_path / "failed" / "job999.json"
    assert failed_video.is_file()
    assert failed_sidecar.is_file()

    retry_payload = json.loads(failed_sidecar.read_text(encoding="utf-8"))
    assert retry_payload["video_path"] == str(failed_video)
    assert retry_payload["title"] == "t"


def test_cleanup_deletes_file(tmp_path):
    media_file = tmp_path / "reject-me.mp4"
    media_file.write_bytes(b"X")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.delete("/cleanup/reject-me.mp4")

    assert response.status_code == 200
    assert not media_file.exists()


def test_cleanup_rejects_path_traversal():
    response = client.delete("/cleanup/..%2F..%2Fetc%2Fpasswd")
    # %2F decodes to "/" before Starlette's router matches {filename}, so a
    # traversal attempt like this never reaches the handler's own 400 check
    # and instead fails route matching with 404 (same ambiguity already
    # accounted for by test_get_media_rejects_path_traversal in
    # test_media_endpoint.py for the identical /media/{filename} pattern).
    assert response.status_code in (400, 404)


@patch("app.main.upload_to_pinterest")
@patch("app.main.upload_video_to_x")
@patch("app.main.upload_to_threads")
@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_video_includes_threads_x_pinterest_when_configured(
    mock_yt, mock_tt, mock_ig, mock_fb, mock_threads, mock_x_vid, mock_pin, tmp_path
):
    video_path = tmp_path / "multi_plat.mp4"
    video_path.write_bytes(b"VIDEO")

    mock_yt.return_value = {"platform": "youtube", "status": "success", "video_id": "y1"}
    mock_tt.return_value = {"platform": "tiktok", "status": "success"}
    mock_ig.return_value = {"platform": "instagram", "status": "success"}
    mock_fb.return_value = {"platform": "facebook", "status": "success"}
    mock_threads.return_value = {"platform": "threads", "status": "success", "post_id": "th1"}
    mock_x_vid.return_value = {"platform": "x", "status": "success", "tweet_id": "tw1"}
    mock_pin.return_value = {"platform": "pinterest", "status": "success", "pin_id": "pin1"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.THREADS_USER_ID = "th_user"
        mock_config.THREADS_ACCESS_TOKEN = "th_tok"
        mock_config.X_CLIENT_ID = "x_cid"
        mock_config.X_REFRESH_TOKEN = "x_tok"
        mock_config.PINTEREST_REFRESH_TOKEN = "p_tok"
        mock_config.PINTEREST_BOARD_ID = "p_board"

        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "multi_plat.mp4",
                "title": "Peak Motivation Rules",
                "description": "Shorts description",
                "tags": ["motivation", "wealth"],
            },
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 7
    platforms = {r["platform"] for r in results}
    assert platforms == {"youtube", "tiktok", "instagram", "facebook", "threads", "x", "pinterest"}
    assert not video_path.exists()
    assert mock_threads.called
    assert mock_x_vid.called
    assert mock_pin.called


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_passes_pinned_comment_to_youtube(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job_pin.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {"platform": "youtube", "status": "success", "video_id": "y1"}
    mock_tt.return_value = {"platform": "tiktok", "status": "error", "error": "x"}
    mock_ig.return_value = {"platform": "instagram", "status": "error", "error": "x"}
    mock_fb.return_value = {"platform": "facebook", "status": "error", "error": "x"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job_pin.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
                "pinned_comment": "Would you pay $20k for status?",
            },
        )

    assert response.status_code == 200
    assert mock_yt.call_args.kwargs["pinned_comment"] == "Would you pay $20k for status?"


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_routes_split_screen_to_tiktok_and_instagram(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job_ss.mp4"
    split_path = tmp_path / "job_ss_splitscreen.mp4"
    video_path.write_bytes(b"CINEMA")
    split_path.write_bytes(b"SPLIT")

    mock_yt.return_value = {"platform": "youtube", "status": "success", "video_id": "y1"}
    mock_tt.return_value = {"platform": "tiktok", "status": "success"}
    mock_ig.return_value = {"platform": "instagram", "status": "success"}
    mock_fb.return_value = {"platform": "facebook", "status": "success"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job_ss.mp4",
                "split_screen_path": str(split_path),
                "split_screen_filename": "job_ss_splitscreen.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    assert response.status_code == 200
    assert mock_yt.call_args.args[0] == str(video_path)
    assert mock_tt.call_args.args[0] == str(split_path)
    assert mock_ig.call_args.args[0] == "job_ss_splitscreen.mp4"
    assert mock_fb.call_args.args[0] == str(video_path)
    assert not video_path.exists()
    assert not split_path.exists()

