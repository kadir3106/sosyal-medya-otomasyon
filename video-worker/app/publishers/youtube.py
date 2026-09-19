import os

from app.http_client import session

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
THUMBNAIL_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    client_id: str,
    client_secret: str,
    refresh_token: str,
    thumbnail_path: str = "",
    privacy_status: str | None = None,
    pinned_comment: str = "",
) -> dict:
    try:
        if privacy_status is not None:
            target_privacy = privacy_status
        elif "PYTEST_CURRENT_TEST" in os.environ:
            target_privacy = "unlisted"
        else:
            target_privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "public")
        access_token = get_access_token(client_id, client_secret, refresh_token)
        video_size = os.path.getsize(video_path)

        init_response = session.post(
            UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_size),
            },
            json={
                "snippet": {
                    "title": title[:100],
                    "description": description,
                    "tags": tags,
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": target_privacy
                },
            },
            timeout=30,
        )
        init_response.raise_for_status()
        upload_url = init_response.headers["Location"]

        with open(video_path, "rb") as video_file:
            upload_response = session.put(
                upload_url,
                headers={"Content-Type": "video/mp4"},
                data=video_file,
                timeout=600,
            )
        upload_response.raise_for_status()
        video_id = upload_response.json()["id"]

        result = {
            "platform": "youtube",
            "status": "success",
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}",
        }
        if thumbnail_path:
            result["thumbnail"] = _set_thumbnail(video_id, thumbnail_path, access_token)
        if pinned_comment:
            result["comment"] = _post_engagement_comment(video_id, pinned_comment, access_token)
        return result
    except Exception as exc:
        return {"platform": "youtube", "status": "error", "error": str(exc)}


COMMENT_URL = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"


def _post_engagement_comment(video_id: str, text: str, access_token: str) -> dict:
    try:
        payload = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": text
                    }
                }
            }
        }
        res = session.post(
            COMMENT_URL,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if res.status_code in (200, 201):
            return {"status": "success", "id": res.json().get("id")}
        return {"status": "error", "code": res.status_code, "detail": res.text[:200]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _set_thumbnail(video_id: str, thumbnail_path: str, access_token: str) -> dict:
    # Video yükleme ana iş; özel kapak ikincil ve başarısız olabilir — küçük
    # kanallarda telefon doğrulaması yapılmamışsa YouTube bunu 403 ile
    # reddediyor. Bu, videonun yayınlanmasını hiçbir zaman engellememeli.
    try:
        with open(thumbnail_path, "rb") as thumb_file:
            response = session.post(
                THUMBNAIL_UPLOAD_URL,
                params={"videoId": video_id},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "image/png",
                },
                data=thumb_file,
                timeout=60,
            )
        response.raise_for_status()
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    response = session.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]
