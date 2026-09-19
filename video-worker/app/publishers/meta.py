import os
import time

from app.http_client import session

from app.tunnel import get_tunnel_url

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def _resolve_public_video_url(video_filename: str, tunnel_log_path: str = "") -> str:
    """Instagram'ın videoyu indirebilmesi için herkese açık URL üretir.

    Prefer the Cloudflare tunnel. Do NOT upload content to third-party hosts
    (catbox.moe) — fail clearly so Telegram can surface a fixable error.
    """
    if tunnel_log_path and os.path.exists(tunnel_log_path):
        try:
            tunnel_url = get_tunnel_url(tunnel_log_path)
            return f"{tunnel_url}/media/{video_filename}"
        except Exception as exc:
            raise RuntimeError(
                f"Instagram public URL unavailable (tunnel failed): {exc}"
            ) from exc

    try:
        tunnel_url = get_tunnel_url(tunnel_log_path)
        return f"{tunnel_url}/media/{video_filename}"
    except Exception as exc:
        raise RuntimeError(
            "Instagram requires a working media tunnel URL; "
            "refusing third-party catbox upload. "
            f"Tunnel error: {exc}"
        ) from exc


def upload_to_instagram(
    video_filename: str,
    caption: str,
    ig_user_id: str,
    page_access_token: str,
    tunnel_log_path: str = "",
) -> dict:
    try:
        video_url = _resolve_public_video_url(video_filename, tunnel_log_path)

        create_response = session.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": page_access_token,
            },
            timeout=30,
        )
        create_response.raise_for_status()
        creation_id = create_response.json()["id"]

        _wait_until_ready(creation_id, page_access_token)

        publish_response = session.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": page_access_token},
            timeout=30,
        )
        publish_response.raise_for_status()
        media_id = publish_response.json()["id"]

        return {"platform": "instagram", "status": "success", "media_id": media_id}
    except Exception as exc:
        return {"platform": "instagram", "status": "error", "error": str(exc)}


def _wait_until_ready(creation_id: str, access_token: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_response = session.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status_response.raise_for_status()
        status_code = status_response.json()["status_code"]

        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram container {creation_id} failed processing")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"Instagram container {creation_id} timed out waiting to process"
    )


def upload_to_facebook(
    video_path: str,
    description: str,
    page_id: str,
    page_access_token: str,
) -> dict:
    try:
        video_size = os.path.getsize(video_path)

        start_response = session.post(
            f"{GRAPH_API_BASE}/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": page_access_token},
            timeout=30,
        )
        start_response.raise_for_status()
        start_data = start_response.json()
        video_id = start_data["video_id"]
        upload_url = start_data["upload_url"]

        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()

        upload_response = session.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {page_access_token}",
                "offset": "0",
                "file_size": str(video_size),
            },
            data=video_bytes,
            timeout=600,
        )
        upload_response.raise_for_status()

        finish_response = session.post(
            f"{GRAPH_API_BASE}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": page_access_token,
            },
            timeout=30,
        )
        finish_response.raise_for_status()

        return {"platform": "facebook", "status": "success", "video_id": video_id}
    except Exception as exc:
        return {"platform": "facebook", "status": "error", "error": str(exc)}
