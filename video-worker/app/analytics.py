from datetime import datetime, timedelta, timezone

from app.http_client import session
from app.publish_log import load_recent_entries
from app.publishers.youtube import get_access_token as get_youtube_access_token

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def build_weekly_report(log_path: str, youtube_creds: dict, meta_creds: dict) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    entries = load_recent_entries(log_path, since_iso=since)

    if not entries:
        return "Son 7 günde yayınlanan video yok."

    lines = [f"📊 Haftalık Rapor ({len(entries)} video)\n"]
    for entry in entries:
        lines.append(f"🎬 {entry['title']}")
        platforms = entry.get("platforms", {})

        youtube = platforms.get("youtube")
        if youtube and youtube.get("status") == "success":
            try:
                stats = _fetch_youtube_stats(youtube["video_id"], youtube_creds)
                lines.append(
                    f"  YouTube: {stats.get('views', '?')} views, "
                    f"{stats.get('likes', '?')} likes, {stats.get('comments', '?')} comments"
                )
            except Exception:
                lines.append("  YouTube: veriler alınamadı")

        instagram = platforms.get("instagram")
        if instagram and instagram.get("status") == "success":
            try:
                stats = _fetch_instagram_stats(instagram["media_id"], meta_creds)
                lines.append(
                    f"  Instagram: {stats.get('plays', '?')} plays, "
                    f"{stats.get('likes', '?')} likes, {stats.get('comments', '?')} comments"
                )
            except Exception:
                lines.append("  Instagram: veriler alınamadı")

        facebook = platforms.get("facebook")
        if facebook and facebook.get("status") == "success":
            try:
                stats = _fetch_facebook_stats(facebook["video_id"], meta_creds)
                lines.append(f"  Facebook: {stats.get('views', '?')} views")
            except Exception:
                lines.append("  Facebook: veriler alınamadı")

        tiktok = platforms.get("tiktok")
        if tiktok and tiktok.get("status") == "success":
            lines.append(
                f"  TikTok: {tiktok.get('privacy_level')} — istatistik için "
                "TikTok uygulamasını kontrol edin (Query API audit sonrası eklenecek)"
            )

        x = platforms.get("x")
        if x and x.get("status") == "success":
            lines.append(
                f"  X: {x.get('url', '—')} — {x.get('tweet_id', '—')} tweet"
            )
        linkedin = platforms.get("linkedin")
        if linkedin and linkedin.get("status") == "success":
            lines.append(
                f"  LinkedIn: {linkedin.get('post_id', '—')} — Professionel içeriği"
            )

        lines.append("")

    return "\n".join(lines)


def _fetch_youtube_stats(video_id: str, creds: dict) -> dict:
    access_token = get_youtube_access_token(
        creds["client_id"], creds["client_secret"], creds["refresh_token"]
    )
    response = session.get(
        YOUTUBE_VIDEOS_URL,
        params={"part": "statistics", "id": video_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        return {}
    stats = items[0]["statistics"]
    return {
        "views": stats.get("viewCount", "0"),
        "likes": stats.get("likeCount", "0"),
        "comments": stats.get("commentCount", "0"),
    }


def _fetch_instagram_stats(media_id: str, creds: dict) -> dict:
    response = session.get(
        f"{GRAPH_API_BASE}/{media_id}/insights",
        params={
            "metric": "plays,likes,comments,shares,saved",
            "access_token": creds["page_access_token"],
        },
        timeout=30,
    )
    response.raise_for_status()
    result = {}
    for item in response.json().get("data", []):
        values = item.get("values", [])
        if values:
            result[item["name"]] = values[0].get("value", 0)
    return result


def _fetch_facebook_stats(video_id: str, creds: dict) -> dict:
    response = session.get(
        f"{GRAPH_API_BASE}/{video_id}",
        params={"fields": "views", "access_token": creds["page_access_token"]},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
