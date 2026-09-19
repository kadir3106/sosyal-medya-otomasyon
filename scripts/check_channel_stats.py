import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.publishers.youtube import get_access_token
import requests


def main():
    print("=" * 60)
    print("📊 PEAK MOTIVATION - YOUTUBE CANLI İSTATİSTİKLERİ")
    print("=" * 60 + "\n")

    token = get_access_token(
        config.YOUTUBE_CLIENT_ID,
        config.YOUTUBE_CLIENT_SECRET,
        config.YOUTUBE_REFRESH_TOKEN,
    )

    # 1. Kanal Genel Durumu
    ch_res = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics", "mine": "true"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    if ch_res.get("items"):
        ch = ch_res["items"][0]
        stats = ch.get("statistics", {})
        print(f"Kanal: {ch['snippet']['title']} ({ch['snippet'].get('customUrl', '')})")
        print(f"Abone Sayısı: {stats.get('subscriberCount', 0)}")
        print(f"Toplam İzlenme: {stats.get('viewCount', 0)}")
        print(f"Toplam Video Sayısı: {stats.get('videoCount', 0)}\n")

    # 2. Yayındaki Videoların Durumu
    video_ids = ["qzdQb0JKjQ8", "CrxErYvCiF0", "pRZcKmoBxIY"]
    v_res = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,status", "id": ",".join(video_ids)},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    print("--- Canlı Shorts Videoları ---")
    for item in v_res.get("items", []):
        vid = item["id"]
        title = item["snippet"]["title"]
        status = item["status"]["privacyStatus"]
        stats = item.get("statistics", {})
        views = stats.get("viewCount", "0")
        likes = stats.get("likeCount", "0")
        comments = stats.get("commentCount", "0")
        print(f"📌 [{vid}] {title}")
        print(f"   Durum: {status} | İzlenme: {views} | Beğeni: {likes} | Yorum: {comments}")
        print(f"   Link: https://youtube.com/shorts/{vid}\n")

    print("=" * 60)


if __name__ == "__main__":
    main()
