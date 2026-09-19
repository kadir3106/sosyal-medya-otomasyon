import os
import re
import time
from pathlib import Path

from app.http_client import session

TOKEN_URL = "https://api.x.com/2/oauth2/token"
MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"
UPLOAD_ENDPOINT = "https://api.x.com/2/media/upload"
TWEET_URL = "https://api.x.com/2/tweets"

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB
POLL_TIMEOUT_SECONDS = 120


def upload_to_x(
    image_path: str,
    text: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """OAuth 2.0 (user context) ile görselli veya videolu tweet atar."""
    if image_path.lower().endswith(".mp4"):
        return upload_video_to_x(
            image_path, text, client_id, client_secret, refresh_token
        )

    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)
        media_id = _upload_media(access_token, image_path)

        return _create_tweet(access_token, text, media_id)
    except Exception as exc:
        return {"platform": "x", "status": "error", "error": str(exc)}


def upload_video_to_x(
    video_path: str,
    text: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    access_token: str | None = None,
) -> dict:
    """X'e Chunked Media Upload protokolüyle MP4 video yükler ve tweet atar."""
    try:
        if not access_token:
            access_token = _get_access_token(client_id, client_secret, refresh_token)
        media_id = _upload_chunked_video(access_token, video_path)

        return _create_tweet(access_token, text, media_id)
    except Exception as exc:
        return {"platform": "x", "status": "error", "error": str(exc)}


def _save_new_refresh_token(new_token: str) -> None:
    try:
        from app.config import config
        config.X_REFRESH_TOKEN = new_token
    except Exception:
        pass
    for cand in [
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]:
        if cand.exists():
            try:
                text = cand.read_text(encoding="utf-8")
                text = re.sub(r"X_REFRESH_TOKEN=.*", f"X_REFRESH_TOKEN={new_token}", text)
                cand.write_text(text, encoding="utf-8")
                break
            except Exception:
                pass


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    response = session.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    new_refresh = data.get("refresh_token")
    if new_refresh:
        _save_new_refresh_token(new_refresh)
    return data["access_token"]


def _upload_media(access_token: str, image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        response = session.post(
            MEDIA_UPLOAD_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={"media_category": "tweet_image"},
            files={"media": image_file},
            timeout=120,
        )
    response.raise_for_status()
    return response.json()["data"]["id"]


def _upload_chunked_video(access_token: str, video_path: str) -> str:
    total_bytes = os.path.getsize(video_path)
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. INIT
    init_res = session.post(
        UPLOAD_ENDPOINT,
        headers=headers,
        data={
            "command": "INIT",
            "total_bytes": str(total_bytes),
            "media_type": "video/mp4",
            "media_category": "tweet_video",
        },
        timeout=30,
    )
    init_res.raise_for_status()
    media_id = init_res.json().get("media_id_string") or str(init_res.json().get("media_id"))

    # 2. APPEND
    segment_index = 0
    with open(video_path, "rb") as vf:
        while True:
            chunk = vf.read(CHUNK_SIZE)
            if not chunk:
                break
            append_res = session.post(
                UPLOAD_ENDPOINT,
                headers=headers,
                data={
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": str(segment_index),
                },
                files={"media": chunk},
                timeout=120,
            )
            append_res.raise_for_status()
            segment_index += 1

    # 3. FINALIZE
    fin_res = session.post(
        UPLOAD_ENDPOINT,
        headers=headers,
        data={"command": "FINALIZE", "media_id": media_id},
        timeout=30,
    )
    fin_res.raise_for_status()
    fin_data = fin_res.json()

    # 4. STATUS Polling (Eğer async işleme gerekiyorsa)
    processing_info = fin_data.get("processing_info")
    if processing_info:
        _wait_for_processing(headers, media_id, processing_info)

    return media_id


def _wait_for_processing(headers: dict, media_id: str, info: dict) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    state = info.get("state")
    check_after = info.get("check_after_secs", 3)

    while time.monotonic() < deadline:
        if state == "succeeded":
            return
        if state == "failed":
            error_msg = info.get("error", {}).get("message", "Video processing failed")
            raise RuntimeError(f"X video processing failed: {error_msg}")

        time.sleep(check_after)

        status_res = session.get(
            UPLOAD_ENDPOINT,
            headers=headers,
            params={"command": "STATUS", "media_id": media_id},
            timeout=30,
        )
        status_res.raise_for_status()
        info = status_res.json().get("processing_info", {})
        state = info.get("state")
        check_after = info.get("check_after_secs", 3)

    raise RuntimeError("X video processing timed out")


def _create_tweet(access_token: str, text: str, media_id: str) -> dict:
    response = session.post(
        TWEET_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"text": text[:280], "media": {"media_ids": [media_id]}},
        timeout=30,
    )
    response.raise_for_status()
    tweet_id = response.json()["data"]["id"]

    return {
        "platform": "x",
        "status": "success",
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
    }
