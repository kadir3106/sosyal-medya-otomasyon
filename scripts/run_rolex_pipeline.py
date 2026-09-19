import asyncio
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add video-worker to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.pipeline import generate_video
from app.publishers.youtube import upload_to_youtube
from app.telegram_bot import send_message, send_video

async def main():
    topic = "The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders"
    job_id = "rolex_dark_wealth"
    
    print(f"=== [1/3] ÜRETİM BAŞLIYOR: '{topic}' ===")
    res = await generate_video(job_id=job_id, topic=topic)
    
    video_path = res["video_path"]
    title = res["title"]
    description = res["description"]
    tags = res["tags"]
    thumb_path = res.get("thumbnail_path", "")
    
    print(f"Video hazır: {video_path}")
    print(f"Başlık: {title}")
    print(f"Açıklama: {description}")
    print(f"Etiketler: {tags}")
    
    print("=== [2/3] YOUTUBE SHORTS YAYINLANIYOR (PUBLIC) ===")
    yt_res = upload_to_youtube(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        thumbnail_path=thumb_path,
        privacy_status="public",
    )
    print("YouTube Yanıtı:", yt_res)
    
    video_url = yt_res.get("url") or f"https://youtube.com/shorts/{yt_res.get('video_id', '')}"
    
    print("=== [3/3] TELEGRAM BİLDİRİMİ GÖNDERİLİYOR ===")
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        tg_text = (
            f"🎬 *Yeni YouTube Shorts Yayında! (Peak Motivation)*\n\n"
            f"📌 *Başlık:* {title}\n"
            f"📺 *İzle:* {video_url}\n\n"
            f"⚡ *Durum:* Herkese Açık (Public)\n"
            f"🎯 *Niş:* Dark Wealth & Secrets"
        )
        try:
            send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, tg_text)
            print("Telegram mesajı gönderildi.")
        except Exception as te:
            print(f"Telegram mesaj hatası: {te}")
            
    print("\n✅ TÜM İŞLEM BAŞARIYLA TAMAMLANDI!")
    print(f"Yayındaki Video: {video_url}")

if __name__ == "__main__":
    asyncio.run(main())
