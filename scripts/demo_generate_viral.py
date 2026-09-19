import asyncio
import os
import sys
from pathlib import Path

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.config import config
from app.pipeline import generate_video

async def main():
    print("🚀 VIRAL VİDEO ÜRETİM TESTİ BAŞLIYOR...")
    print(f"📌 Dil: {config.VIDEO_LANG}")
    print(f"📌 Ses: {config.VIDEO_VOICE or 'default'}")
    print(f"📌 Model: {config.OPENROUTER_MODEL}")

    # Dark Stoic / Viral Power Konsepti
    test_topic = "The Rule of Unshakable Focus: Marcus Aurelius had one brutal rule about people who waste your time"
    job_id = "demo_stoic_focus"

    # Yerel çıktı dizini ayarla
    media_dir = Path(__file__).resolve().parent.parent / "video-output"
    media_dir.mkdir(parents=True, exist_ok=True)
    config.MEDIA_DIR = str(media_dir)
    config.BGM_DIR = str(media_dir / "audio" / "bgm")

    try:
        result = await generate_video(job_id, topic=test_topic)
        print("\n🎉 VİDEO BAŞARIYLA ÜRETİLDİ!")
        print("=" * 60)
        print(f"🎬 Başlık: {result['title']}")
        print(f"📝 Açıklama: {result['description']}")
        print(f"🏷️ Etiketler: {result['tags']}")
        print(f"📁 Video Dosyası: {result['video_path']}")
        print(f"🖼️ Kapak Resmi: {result['thumbnail_path']}")
        print("=" * 60)
        print(f"\nVideoyu doğrudan açıp izleyebilirsin: {result['video_path']}")
    except Exception as exc:
        print(f"❌ Üretim hatası: {exc}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
