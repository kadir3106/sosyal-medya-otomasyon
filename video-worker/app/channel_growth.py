"""
Kanal Büyüme, Analiz ve Otonom İyileştirme Motoru (Channel Growth Engine)

Peak Motivation YouTube kanalının canlı metriklerini izler,
neyin tutup neyin tutmadığını analiz eder, ve asistanın (Miko)
kullanıcıyla doğrudan bir danışman gibi konuşmasını sağlayacak
içgörüler ve yeni viral konular üretir.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import config
from app.http_client import session
from app.publishers.youtube import get_access_token

logger = logging.getLogger(__name__)


def fetch_channel_analytics() -> dict[str, Any]:
    """YouTube API'den kanal ve tüm Shorts videolarının güncel metriklerini çeker."""
    token = get_access_token(
        config.YOUTUBE_CLIENT_ID,
        config.YOUTUBE_CLIENT_SECRET,
        config.YOUTUBE_REFRESH_TOKEN,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Kanal Genel Bilgisi
    ch_res = session.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics,contentDetails", "mine": "true"},
        headers=headers,
        timeout=15,
    ).json()

    items = ch_res.get("items", [])
    if not items:
        return {"error": "Kanal bulunamadı."}

    channel_item = items[0]
    snippet = channel_item.get("snippet", {})
    stats = channel_item.get("statistics", {})
    uploads_id = channel_item["contentDetails"]["relatedPlaylists"]["uploads"]

    channel_info = {
        "title": snippet.get("title", "Peak Motivation"),
        "custom_url": snippet.get("customUrl", "@peakmotivation-o4e"),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "total_videos": int(stats.get("videoCount", 0)),
    }

    # 2. Yüklenen Videolar
    pl_res = session.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        params={"part": "snippet,status", "playlistId": uploads_id, "maxResults": 20},
        headers=headers,
        timeout=15,
    ).json()

    playlist_items = pl_res.get("items", [])
    if not playlist_items:
        return {"channel": channel_info, "videos": []}

    video_ids = [it["snippet"]["resourceId"]["videoId"] for it in playlist_items]
    vids_res = session.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,status", "id": ",".join(video_ids)},
        headers=headers,
        timeout=15,
    ).json()

    videos = []
    for v in vids_res.get("items", []):
        v_stats = v.get("statistics", {})
        v_snippet = v.get("snippet", {})
        v_status = v.get("status", {})
        videos.append({
            "id": v["id"],
            "title": v_snippet.get("title", ""),
            "views": int(v_stats.get("viewCount", 0)),
            "likes": int(v_stats.get("likeCount", 0)),
            "comments": int(v_stats.get("commentCount", 0)),
            "privacy": v_status.get("privacyStatus", "public"),
            "published_at": v_snippet.get("publishedAt", ""),
            "url": f"https://youtube.com/shorts/{v['id']}",
        })

    # En çok izlenene göre sırala
    videos.sort(key=lambda x: x["views"], reverse=True)

    return {
        "channel": channel_info,
        "videos": videos,
    }


def analyze_channel_growth() -> dict[str, Any]:
    """Kanal performansını analiz eder ve büyüme içgörüleri çıkarır."""
    data = fetch_channel_analytics()
    if "error" in data:
        return data

    videos = data.get("videos", [])
    channel = data.get("channel", {})

    top_performer = videos[0] if videos else None
    avg_views = (sum(v["views"] for v in videos) / len(videos)) if videos else 0

    # Kanca & Kelime Analizi
    insights = []
    if top_performer and top_performer["views"] > 50:
        insights.append(
            f"En çok izlenen video '{top_performer['title']}' ({top_performer['views']} izlenme). "
            f"Merak uyandıran soru ve 'yasak/gizli gerçek' (Forbidden Truth/Secrets) temaları algoritmada daha iyi retention sağlıyor."
        )
    else:
        insights.append(
            "Kanal henüz başlangıç aşamasında. YouTube Shorts algoritması videoları 24-72 saat içinde test havuzlarına sokuyor."
        )

    return {
        "channel": channel,
        "videos": videos,
        "top_performer": top_performer,
        "avg_views": round(avg_views, 1),
        "insights": insights,
    }


def get_conversational_channel_report() -> str:
    """Miko veya başka bir asistanın kullanıcıya doğrudan doğal dille anlatabileceği samimi rapor."""
    try:
        analysis = analyze_channel_growth()
        if "error" in analysis:
            return f"Kanal verilerine şu an ulaşılamıyor: {analysis['error']}"

        ch = analysis["channel"]
        vids = analysis["videos"]
        top = analysis["top_performer"]

        lines = [
            f"Kanalımız **{ch['title']}** ({ch['custom_url']}) şu an toplam **{ch['total_views']}** izlenmeye ve **{ch['subscribers']}** aboneye ulaştı.",
            "",
            "🎬 **Son Videoların Durumu:**",
        ]

        for v in vids[:5]:
            status_emoji = "🔥" if v["views"] >= 100 else ("📈" if v["views"] > 10 else "⏳")
            lines.append(f"• {status_emoji} **{v['title']}** — {v['views']} izlenme, {v['likes']} beğeni")

        lines.append("")
        if top and top["views"] >= 50:
            lines.append(f"💡 **Büyüme İçgörüsü:** En iyi performans gösteren videomuz **'{top['title']}'** ({top['views']} izlenme). 'Yasak gerçekler' ve lüks/güç markalarının arkasındaki gizemler izleyiciyi daha çok tutuyor.")
        else:
            lines.append("💡 **Büyüme İçgörüsü:** Yeni yüklenen videolar henüz Shorts test rafında (Shorts Shelf). Algoritma izleyicileri test ettikçe izlenmeler 1-2 gün içinde aniden fırlama eğilimindedir.")

        lines.append("\n🚀 **Sonraki Adım:** Saat 18:30'da sıradaki gizem ve güç temalı Shorts otomatik olarak yayına girecek.")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("Kanal raporu oluşturulurken hata:")
        return f"Kanal analizi alınırken bir sorun oluştu: {e}"


def get_winning_context_for_prompt() -> str:
    """YouTube analitiğinden en çok izlenen konsepti çıkarıp LLM promptuna rehber bellek olarak ekler."""
    try:
        data = analyze_channel_growth()
        top = data.get("top_performer")
        if top and top.get("views", 0) > 25:
            return (
                f"\n# Historical Winning Pattern from Channel Analytics:\n"
                f"The highest-performing video on this channel is '{top['title']}' with {top['views']} views. "
                f"Double down on this high-stakes tension, forbidden knowledge, and counter-intuitive framing.\n"
            )
    except Exception:
        pass
    return ""

