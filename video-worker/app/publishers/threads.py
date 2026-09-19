import time

from app.http_client import session
from app.tunnel import get_tunnel_url

THREADS_API_BASE = "https://graph.threads.net/v1.0"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def upload_to_threads(
    video_filename: str,
    caption: str,
    threads_user_id: str,
    access_token: str,
    tunnel_log_path: str,
) -> dict:
    """Meta Threads API üzerinden dikey video paylaşır.

    Instagram Reels gibi, video dosyası Cloudflare tüneli üzerinden
    (GET /media/{video_filename}) çekilir.
    """
    if not threads_user_id or not access_token:
        return {
            "platform": "threads",
            "status": "error",
            "error": "threads_user_id or access_token missing",
        }

    try:
        tunnel_url = get_tunnel_url(tunnel_log_path)
        video_url = f"{tunnel_url}/media/{video_filename}"

        create_response = session.post(
            f"{THREADS_API_BASE}/{threads_user_id}/threads",
            data={
                "media_type": "VIDEO",
                "video_url": video_url,
                "text": caption[:500],
                "access_token": access_token,
            },
            timeout=30,
        )
        create_response.raise_for_status()
        creation_id = create_response.json()["id"]

        _wait_until_ready(creation_id, access_token)

        publish_response = session.post(
            f"{THREADS_API_BASE}/{threads_user_id}/threads_publish",
            data={"creation_id": creation_id, "access_token": access_token},
            timeout=30,
        )
        publish_response.raise_for_status()
        post_id = publish_response.json()["id"]

        return {
            "platform": "threads",
            "status": "success",
            "post_id": post_id,
            "url": f"https://www.threads.net/post/{post_id}",
        }
    except Exception as exc:
        return {"platform": "threads", "status": "error", "error": str(exc)}


def _wait_until_ready(creation_id: str, access_token: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_response = session.get(
            f"{THREADS_API_BASE}/{creation_id}",
            params={"fields": "status,error_message", "access_token": access_token},
            timeout=30,
        )
        status_response.raise_for_status()
        data = status_response.json()
        status = data.get("status")

        if status == "FINISHED":
            return
        if status == "ERROR":
            error_msg = data.get("error_message", "Unknown container error")
            raise RuntimeError(f"Threads container {creation_id} failed: {error_msg}")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"Threads container {creation_id} timed out waiting to process"
    )
