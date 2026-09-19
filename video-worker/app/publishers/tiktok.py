import json
import os
import tempfile
from pathlib import Path

import requests

TOKEN_REFRESH_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"


def upload_to_tiktok(
    video_path: str,
    title: str,
    client_key: str,
    client_secret: str,
    token_path: str,
    audited: bool = False,
) -> dict:
    try:
        access_token = _refresh_access_token(client_key, client_secret, token_path)
        video_size = os.path.getsize(video_path)
        privacy_level = "PUBLIC_TO_EVERYONE" if audited else "SELF_ONLY"

        init_response = requests.post(
            INIT_UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": title[:150],
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1,
                },
            },
            timeout=30,
        )
        init_response.raise_for_status()
        init_data = init_response.json()["data"]
        publish_id = init_data["publish_id"]
        upload_url = init_data["upload_url"]

        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()

        upload_response = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            },
            data=video_bytes,
            timeout=600,
        )
        upload_response.raise_for_status()

        return {
            "platform": "tiktok",
            "status": "success",
            "publish_id": publish_id,
            "privacy_level": privacy_level,
        }
    except Exception as exc:
        return {"platform": "tiktok", "status": "error", "error": str(exc)}


def _resolve_token_path(token_path: str) -> Path:
    p = Path(token_path)
    if p.exists():
        return p
    for cand in [
        Path(".tiktok_token.json"),
        Path("video-output/tiktok_token.json"),
        Path(__file__).resolve().parent.parent.parent / ".tiktok_token.json",
        Path(__file__).resolve().parent.parent.parent / "video-output" / "tiktok_token.json",
    ]:
        if cand.exists():
            return cand
    return p


def _refresh_access_token(
    client_key: str, client_secret: str, token_path: str
) -> str:
    actual_path = _resolve_token_path(token_path)
    stored = json.loads(actual_path.read_text(encoding="utf-8"))
    current_refresh_token = stored["refresh_token"]

    response = requests.post(
        TOKEN_REFRESH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": current_refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # TikTok rotates the refresh token on every use — persist the new one.
    # Written atomically (tmp file + os.replace) so a process kill mid-write
    # can never leave a truncated/corrupted token file: the old refresh
    # token is already dead server-side at this point, so a corrupted file
    # would be a permanent lockout rather than a retryable failure.
    token_dir = Path(token_path).parent
    fd, tmp_path = tempfile.mkstemp(dir=token_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps({"refresh_token": data["refresh_token"]}))
        os.replace(tmp_path, token_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    return data["access_token"]
