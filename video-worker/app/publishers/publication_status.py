"""Platforma "bu yayın gerçekten oldu mu?" diye soran gerçek API çağrıları.

Her çözümleyici bir `inflight` kimliği alır ve `PublishStatus` döndürür.
Bilinmeyen bir alan gördüğünde tahmin etmez: `unknown` döner. Yanlış
`published` demek operatörün yayını kaçırmasına, yanlış `failed` demek aynı
videonun iki kez yayınlanmasına yol açar — ikisi de kabul edilemez.

API kaynakları (doğrulandı):
- TikTok: `GET /v2/post/publish/status/fetch/` (gövdede `publish_id`)
- YouTube: `GET /youtube/v3/videos?part=status,processingDetails&id=...`
"""
from __future__ import annotations

from app.http_client import session
from app.publish_status import FAILED, PENDING, PUBLISHED, UNKNOWN, PublishStatus

TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# TikTok `status` alanının belgelenmiş değerleri. Listede olmayan bir değer
# gelirse `unknown` deriz — yeni bir durum uydurmak riskli.
_TIKTOK_SCHEDULED = "PUBLISH_COMPLETE"
_TIKTOK_FAILED = "FAILED"
_TIKTOK_IN_PROGRESS = (
    "PROCESSING_UPLOAD",
    "PROCESSING_DOWNLOAD",
    "SEND_TO_USER_INBOX",
)


def resolve_tiktok(identity: dict) -> PublishStatus:
    """TikTok: `publish_id` ile durum sorgusu.

    `fail_reason` alanı varsa yayın gerçekten düşmüş demektir; bu durumda
    yeniden denemek güvenli.
    """
    publish_id = str(identity.get("publish_id") or "")
    if not publish_id:
        return PublishStatus("tiktok", UNKNOWN, detail="publish_id missing")
    access_token = str(identity.get("access_token") or "")
    if not access_token:
        return PublishStatus("tiktok", UNKNOWN, detail="access_token missing")

    response = session.post(
        TIKTOK_STATUS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=30,
    )
    if response.status_code >= 400:
        return PublishStatus(
            "tiktok", UNKNOWN, detail=f"http {response.status_code}"
        )
    data = (response.json() or {}).get("data") or {}
    raw = str(data.get("status") or "").upper()

    if raw == _TIKTOK_SCHEDULED:
        ids = data.get("publicaly_available_post_id") or data.get("post_id") or []
        url = ""
        if isinstance(ids, list) and ids:
            url = f"https://www.tiktok.com/video/{ids[0]}"
        return PublishStatus("tiktok", PUBLISHED, detail=raw, url=url)
    if raw == _TIKTOK_FAILED:
        return PublishStatus(
            "tiktok", FAILED, detail=str(data.get("fail_reason") or raw)
        )
    if raw in _TIKTOK_IN_PROGRESS:
        return PublishStatus("tiktok", PENDING, detail=raw)
    return PublishStatus("tiktok", UNKNOWN, detail=raw or "empty status")


def resolve_youtube(identity: dict) -> PublishStatus:
    """YouTube: `video_id` ile `status`/`processingDetails`.

    Video işlenmeye devam ediyorsa yayın *başlamış* demektir ama henüz
    izlenebilir değil; bu yüzden `pending`.
    """
    video_id = str(identity.get("video_id") or "")
    if not video_id:
        return PublishStatus("youtube", UNKNOWN, detail="video_id missing")
    access_token = str(identity.get("access_token") or "")
    if not access_token:
        return PublishStatus("youtube", UNKNOWN, detail="access_token missing")

    response = session.get(
        YOUTUBE_VIDEOS_URL,
        params={"part": "status,processingDetails", "id": video_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code >= 400:
        return PublishStatus(
            "youtube", UNKNOWN, detail=f"http {response.status_code}"
        )
    items = (response.json() or {}).get("items") or []
    if not items:
        # Kimliği biliyoruz ama video yok: yüklenmemiş. `failed` demek güvenli
        # DEĞİL — yükleme henüz görünür olmayabilir. Bilinmiyor bırakıyoruz.
        return PublishStatus("youtube", UNKNOWN, detail="video not found yet")

    item = items[0]
    status = item.get("status") or {}
    upload_status = str(status.get("uploadStatus") or "")
    processing = str(
        (item.get("processingDetails") or {}).get("processingStatus") or ""
    )
    if upload_status == "failed":
        return PublishStatus(
            "youtube", FAILED, detail=str(status.get("failureReason") or "upload failed")
        )
    if upload_status == "processed" and processing in ("", "succeeded"):
        return PublishStatus(
            "youtube",
            PUBLISHED,
            detail=f"{upload_status}/{processing or 'n/a'}",
            url=f"https://youtube.com/shorts/{video_id}",
        )
    # uploaded / processing
    return PublishStatus(
        "youtube", PENDING, detail=f"{upload_status}/{processing or 'n/a'}"
    )


# Platform adı → çözümleyici. Burada olmayan platform için `query` `unknown`
# döner (yanlış beyandan iyidir).
RESOLVERS = {
    "tiktok": resolve_tiktok,
    "youtube": resolve_youtube,
}


def _tiktok_credentials(config) -> dict:
    """TikTok için taze access token — token dosyası döndürücü tarafından yenilenir."""
    from app.publishers.tiktok import _refresh_access_token

    return {
        "access_token": _refresh_access_token(
            config.TIKTOK_CLIENT_KEY,
            config.TIKTOK_CLIENT_SECRET,
            config.TIKTOK_TOKEN_PATH,
        )
    }


def _youtube_credentials(config) -> dict:
    """YouTube için taze access token (refresh_token akışı)."""
    from app.publishers.youtube import get_access_token

    return {
        "access_token": get_access_token(
            config.YOUTUBE_CLIENT_ID,
            config.YOUTUBE_CLIENT_SECRET,
            config.YOUTUBE_REFRESH_TOKEN,
        )
    }


# Token'lar diskte tutulmuyor; sorgu anında burada üretiliyor. Bir platform
# burada yoksa durum sorgusu yapılamaz ve `unknown` döner.
CREDENTIAL_REFRESHERS = {
    "tiktok": _tiktok_credentials,
    "youtube": _youtube_credentials,
}
