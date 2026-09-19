"""YouTube'a daha önce yüklenmiş videoları diğer platformlara (X, Facebook, Instagram) aktarma aracı.

Yeniden video üretimi veya YouTube'a tekrar yükleme YAPMAZ.
'video-output/' dizinindeki hazır MP4'leri doğrudan hedeflenen sosyal medya platformlarına yükler.
"""

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.publishers.x import upload_video_to_x, _get_access_token
from app.publishers.meta import upload_to_facebook
from app.telegram_bot import send_message

READY_VIDEOS = [
    {
        "filename": "rolex_dark_wealth.mp4",
        "title": "Rolex Has No Owners? The Forbidden Truth",
        "description": "Rolex is owned 100% by a private Swiss trust with zero public shareholders. #DarkWealth #Rolex #Secrets #Luxury #Money",
    },
    {
        "filename": "viral_mcdonalds_real_estate.mp4",
        "title": "McDonald's Is Actually A Secret Scam",
        "description": "How the biggest fast food chain in the world became the largest real estate empire. #McDonalds #BusinessSecrets #DarkWealth #RealEstate",
    },
    {
        "filename": "auto_20260916_183319.mp4",
        "title": "They Own No Factories",
        "description": "The Red Bull Strategy: How they make billions without owning a single drink factory. #RedBull #BusinessStrategy #Marketing #DarkWealth",
    },
    {
        "filename": "auto_20260916_184602.mp4",
        "title": "The De Beers Lie: Rocks as Currency",
        "description": "How an advertising cartel convinced the world that rocks are precious. #DeBeers #DarkWealth #MarketingSecrets #Economy",
    },
]


def republish_all():
    print("=" * 65)
    print("🚀 YOUTUBE'DAKİ VİDEOLARI DİĞER PLATFORMLARA YÜKLEME ARACI")
    print("=" * 65 + "\n")

    media_dir = Path(__file__).resolve().parent.parent / "video-output"

    # 1. X Access Token al (Tek seferde alınır, rotasyon token'ı otomatik .env'e kaydedilir)
    x_access_token = None
    if config.X_CLIENT_ID and config.X_REFRESH_TOKEN:
        try:
            x_access_token = _get_access_token(
                config.X_CLIENT_ID, config.X_CLIENT_SECRET, config.X_REFRESH_TOKEN
            )
            print("  - X (Twitter): ✅ Token Doğrulandı & Oturum Hazır")
        except Exception as e:
            print(f"  - X (Twitter): ❌ Token Geçersiz veya Süresi Dolmuş ({e})")
    else:
        print("  - X (Twitter): ⚪ Bilgiler eksik")

    # 2. Meta Durumu
    meta_valid = False
    if config.META_PAGE_ACCESS_TOKEN and config.META_PAGE_ID:
        import requests
        try:
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{config.META_PAGE_ID}",
                params={"access_token": config.META_PAGE_ACCESS_TOKEN},
                timeout=15,
            )
            meta_valid = r.ok
            if meta_valid:
                print("  - Meta (Facebook): ✅ Token Geçerli")
            else:
                print("  - Meta (Facebook): ❌ Token Süresi Dolmuş")
        except Exception:
            meta_valid = False

    print()

    if not x_access_token and not meta_valid:
        print("⚠️ DİKKAT: X ve Meta token'larının süresi dolmuş!")
        print("   Videoları yükleyebilmek için token'ı yenilemeniz gerekiyor:")
        print("   👉 X (Twitter) için: 'python scripts/x_oauth_helper.py' komutunu çalıştırın.\n")
        return

    for item in READY_VIDEOS:
        video_path = media_dir / item["filename"]
        if not video_path.exists():
            print(f"⚠️ Dosya bulunamadı: {item['filename']}, atlanıyor...")
            continue

        print(f"\n🎬 İşleniyor: '{item['title']}' ({item['filename']})")

        # 1. X (Twitter) Yüklemesi
        if x_access_token:
            print("   🐦 X'e (Twitter) video yükleniyor (Chunked Video Upload)...")
            x_res = upload_video_to_x(
                video_path=str(video_path),
                text=f"{item['title']}\n\n{item['description']}",
                client_id=config.X_CLIENT_ID,
                client_secret=config.X_CLIENT_SECRET,
                refresh_token=config.X_REFRESH_TOKEN,
                access_token=x_access_token,
            )
            if x_res.get("status") == "success":
                print(f"   ✅ X'e Yüklendi! Tweet: {x_res.get('url')}")
            else:
                print(f"   ❌ X Hatası: {x_res.get('error')}")

        # 2. Facebook Reels Yüklemesi
        if meta_valid and config.META_PAGE_ID:
            print("   👥 Facebook Reels'e yükleniyor...")
            fb_res = upload_to_facebook(
                video_path=str(video_path),
                description=f"{item['title']}\n\n{item['description']}",
                page_id=config.META_PAGE_ID,
                page_access_token=config.META_PAGE_ACCESS_TOKEN,
            )
            if fb_res.get("status") == "success":
                print(f"   ✅ Facebook Reels'e Yüklendi! Video ID: {fb_res.get('video_id')}")
            else:
                print(f"   ❌ Facebook Hatası: {fb_res.get('error')}")

    print("\n🎉 Tüm gönderimler tamamlandı!")


if __name__ == "__main__":
    republish_all()
