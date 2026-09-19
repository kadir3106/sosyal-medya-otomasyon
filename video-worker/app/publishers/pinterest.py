import base64
import os
import time

from app.http_client import session

PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINTEREST_MEDIA_URL = "https://api.pinterest.com/v5/media"
PINTEREST_PINS_URL = "https://api.pinterest.com/v5/pins"

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def upload_to_pinterest(
    video_path: str,
    title: str,
    description: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    board_id: str,
) -> dict:
    """Pinterest API v5 ile dikey Video Pin oluşturur."""
    if not all([client_id, client_secret, refresh_token, board_id]):
        return {
            "platform": "pinterest",
            "status": "error",
            "error": "Pinterest credentials or board_id missing",
        }

    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)
        media_id = _register_and_upload_video(access_token, video_path)

        pin_data = _create_pin(access_token, board_id, title, description, media_id)
        pin_id = pin_data.get("id")

        return {
            "platform": "pinterest",
            "status": "success",
            "pin_id": pin_id,
            "url": f"https://www.pinterest.com/pin/{pin_id}/",
        }
    except Exception as exc:
        return {"platform": "pinterest", "status": "error", "error": str(exc)}


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = session.post(
        PINTEREST_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _register_and_upload_video(access_token: str, video_path: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Register media upload
    reg_res = session.post(
        PINTEREST_MEDIA_URL,
        headers={**headers, "Content-Type": "application/json"},
        json={"media_type": "video"},
        timeout=30,
    )
    reg_res.raise_for_status()
    reg_data = reg_res.json()
    media_id = reg_data["media_id"]
    upload_url = reg_data["upload_url"]
    upload_params = reg_data.get("upload_parameters", {})

    # 2. Upload file to S3 upload_url
    with open(video_path, "rb") as vf:
        upload_res = session.post(
            upload_url,
            data=upload_params,
            files={"file": vf},
            timeout=300,
        )
        upload_res.raise_for_status()

    # 3. Wait until media status is succeeded
    _wait_for_media_processing(headers, media_id)
    return media_id


def _wait_for_media_processing(headers: dict, media_id: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    status_url = f"{PINTEREST_MEDIA_URL}/{media_id}"

    while time.monotonic() < deadline:
        res = session.get(status_url, headers=headers, timeout=30)
        res.raise_for_status()
        status = res.json().get("status")

        if status == "succeeded":
            return
        if status == "failed":
            raise RuntimeError(f"Pinterest media {media_id} failed processing")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(f"Pinterest media {media_id} timed out waiting to process")


def _create_pin(
    access_token: str, board_id: str, title: str, description: str, media_id: str
) -> dict:
    response = session.post(
        PINTEREST_PINS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "board_id": board_id,
            "title": title[:100],
            "description": description[:800],
            "media_source": {
                "source_type": "video_id",
                "media_id": media_id,
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
