"""
Peak Motivation - Otonom Günlük YouTube Shorts Üretim ve Yayın Motoru

Bu betik:
1. 'topics_dark_wealth.json' dosyasından sıradaki konuyu otonom seçer (daha önce kullanılanları atlar).
2. Kling AI + Pexels HD, ElevenLabs ve Karaoke ASS altyazıyla 1080x1920 dikey Short render eder.
3. 'Peak Motivation' YouTube kanalına doğrudan 'public' olarak yükler.
4. Telegram botuna canlı link ile anında bildirim gönderir.
5. Her gün 18:30 TSİ'de otomatik çalışır ya da '--now' ile anında tetiklenir.
"""

import argparse
import asyncio
import datetime
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.pipeline import generate_video
from app.publishers.youtube import upload_to_youtube
from app.telegram_bot import send_message
from app.topics import release_topic, select_next_topic


async def execute_daily_run(use_trend: bool = False):
    print("\n" + "=" * 60)
    print(f"🚀 OTONOM YAYIN MOTORU BAŞLADI: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    media_dir = Path(config.MEDIA_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    
    topics_file = Path(__file__).resolve().parent.parent / "video-worker" / "data" / "topics_dark_wealth.json"
    state_file = media_dir / "used_topics.json"
    
    # Sıradaki konuyu belirle (Trend veya Havuz)
    if use_trend:
        try:
            from app.trends import get_trending_viral_topic
            print("🌐 Canlı Google Trends taranıyor (US & Global)...")
            topic = get_trending_viral_topic(config.OPENROUTER_API_KEY, geo="US")
            print(f"🔥 Canlı Sıcak Trend Konusu: {topic}")
        except Exception as te:
            print(f"⚠️ Trend çekme uyarısı ({te}), havuzdan devam ediliyor.")
            topic = select_next_topic(str(topics_file), str(state_file))
            print(f"🎯 Havuzdan Seçilen Konu: {topic}")
    else:
        topic = select_next_topic(str(topics_file), str(state_file))
        print(f"🎯 Havuzdan Seçilen Konu: {topic}")

    job_id = f"auto_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"🆔 Görev Kimliği: {job_id}")
    
    # 1. Video Üret
    print("\n🎬 [1/3] Video Üretiliyor (Kling AI + ElevenLabs + 1080p)...")
    try:
        res = await generate_video(job_id=job_id, topic=topic)
    except Exception as ge:
        release_topic(topic, str(state_file))
        print(f"❌ Video üretim hatası: {ge}")
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            try:
                send_message(
                    config.TELEGRAM_BOT_TOKEN,
                    config.TELEGRAM_CHAT_ID,
                    f"⚠️ *Peak Motivation - Video Üretim Hatası*\n\n📌 *Konu:* {topic}\n❌ *Hata:* `{str(ge)[:120]}`",
                )
            except Exception:
                pass
        raise
    
    video_path = res["video_path"]
    split_video_path = res.get("split_screen_path") or video_path
    title = res["title"]
    description = res["description"]
    tags = res["tags"]
    pinned_comment = res.get("pinned_comment", "")
    thumb_path = res.get("thumbnail_path", "")
    
    print(f"✅ Video Hazır (Sinematik): {video_path}")
    if split_video_path != video_path:
        print(f"⚡ Video Hazır (TikTok Split-Screen ASMR): {split_video_path}")
    print(f"📌 Başlık: {title}")
    if pinned_comment:
        print(f"💬 Sabitlenmiş Yorum Kancası: {pinned_comment}")
    
    # İsteğe bağlı: Telegram Yönetmen Modu (Yayın Öncesi Önizleme & Onay Butonları)
    if director_mode and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        from app.telegram_bot import send_message, get_updates, answer_callback_query
        print("\n📲 [Yönetmen Modu] Telegram'a onay ve önizleme gönderiliyor...")
        reply_markup = {
            "inline_keyboard": [
                [{"text": "🚀 Hemen Tüm Kanallara Yayınla", "callback_data": f"pub:{job_id}"}],
                [{"text": "❌ İptal Et / Pas Geç", "callback_data": f"cancel:{job_id}"}]
            ]
        }
        dir_caption = (
            f"🎬 *Peak Motivation - Yönetmen Önizlemesi*\n\n"
            f"📌 *Başlık:* {title}\n"
            f"🎯 *Konsept:* {topic}\n"
            f"💬 *Kanca:* {pinned_comment}\n"
            f"⚡ *Formatlar:* Sinematik (YouTube/FB) + Split-Screen (TikTok/IG)\n\n"
            f"Yayına almak için aşağıdaki butona basın:"
        )
        send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, dir_caption, reply_markup=reply_markup)

        print("⏳ Telegram'dan onay bekleniyor (Maksimum 3 dakika, yanıt gelmezse otomatik yayınlanır)...")
        approved = False
        start_wait = time.time()
        offset = 0
        while time.time() - start_wait < 180:
            await asyncio.sleep(3)
            try:
                upds = get_updates(config.TELEGRAM_BOT_TOKEN, offset=offset, timeout=2)
                for u in upds.get("result", []):
                    offset = u["update_id"] + 1
                    cq = u.get("callback_query")
                    if cq:
                        cdata = cq.get("data", "")
                        cq_id = cq.get("id")
                        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cq_id)
                        if cdata.startswith(f"pub:{job_id}"):
                            send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, "🚀 *Onay Alındı!* Kanallara yükleme başlatılıyor...")
                            approved = True
                            break
                        elif cdata.startswith(f"cancel:{job_id}"):
                            send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, "❌ *Yayın iptal edildi.*")
                            return None
            except Exception:
                pass
            if approved:
                break

        if not approved:
            print("⏱️ Zaman aşımı: Yanıt gelmedi, otonom yayına devam ediliyor.")

    # 2. Çoklu Platform Yayınlama (YouTube Shorts öncelikli)
    print("\n📺 [2/3] Sosyal Medya Kanallarına Yayınlanıyor...")
    platforms_status = []
    
    # YouTube Shorts (Ana Kanal - Sinematik Hollywood formatı)
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
        pinned_comment=pinned_comment,
    )
    video_id = yt_res.get("video_id")
    video_url = yt_res.get("url") or f"https://youtube.com/shorts/{video_id}"
    print(f"✅ YouTube Yanıtı: {yt_res.get('status')} | URL: {video_url}")
    platforms_status.append(f"🔴 *YouTube Shorts:* {'Yayında (Public) ✅' if yt_res.get('status') == 'success' else 'Hata ❌'}\n   🔗 {video_url}")
    
    # Meta / Instagram Reels (Split-Screen yüksek retention formatı)
    if config.META_PAGE_ACCESS_TOKEN and config.META_IG_USER_ID:
        try:
            from app.publishers.meta import upload_to_instagram
            ig_res = upload_to_instagram(
                video_filename=Path(split_video_path).name,
                caption=f"{title}\n\n{description}\n\n#DarkWealth #Shorts #Secrets",
                ig_user_id=config.META_IG_USER_ID,
                page_access_token=config.META_PAGE_ACCESS_TOKEN,
                tunnel_log_path=config.TUNNEL_LOG_PATH,
            )
            if ig_res.get("status") == "success":
                print(f"✅ Instagram Reels: Yayında (ID: {ig_res.get('media_id')})")
                platforms_status.append(f"📸 *Instagram Reels:* Yayında ✅")
            else:
                print(f"⚠️ Instagram Uyarısı: {ig_res.get('error')}")
                platforms_status.append(f"📸 *Instagram Reels:* ⚠️ {ig_res.get('error', '')[:40]}")
        except Exception as ige:
            print(f"⚠️ Instagram Hatası: {ige}")

    # Facebook Reels (Meta Sayfa - Sinematik format)
    if config.META_PAGE_ACCESS_TOKEN and config.META_PAGE_ID:
        try:
            from app.publishers.meta import upload_to_facebook
            fb_res = upload_to_facebook(
                video_path=video_path,
                description=f"{title}\n\n{description}\n\n#DarkWealth #Shorts #Secrets",
                page_id=config.META_PAGE_ID,
                page_access_token=config.META_PAGE_ACCESS_TOKEN,
            )
            if fb_res.get("status") == "success":
                print(f"✅ Facebook Reels: Yayında (ID: {fb_res.get('video_id')})")
                platforms_status.append(f"📘 *Facebook Reels:* Yayında ✅")
            else:
                print(f"⚠️ Facebook Uyarısı: {fb_res.get('error')}")
                platforms_status.append(f"📘 *Facebook Reels:* ⚠️ {fb_res.get('error', '')[:40]}")
        except Exception as fbe:
            print(f"⚠️ Facebook Hatası: {fbe}")
            
    # TikTok (Split-Screen yüksek retention formatı)
    tiktok_token_path = Path(config.TIKTOK_TOKEN_PATH)
    if not tiktok_token_path.is_file():
        tiktok_token_path = media_dir / "tiktok_token.json"
    
    # 1. Önce resmi API tokenı varsa dene
    if tiktok_token_path.is_file() and config.TIKTOK_CLIENT_KEY:
        try:
            from app.publishers.tiktok import upload_to_tiktok
            tt_res = upload_to_tiktok(
                video_path=split_video_path,
                title=title,
                client_key=config.TIKTOK_CLIENT_KEY,
                client_secret=config.TIKTOK_CLIENT_SECRET,
                token_path=str(tiktok_token_path),
                audited=config.TIKTOK_AUDITED,
            )
            if tt_res.get("status") == "success":
                print(f"✅ TikTok (API): Yayında")
                platforms_status.append(f"🎵 *TikTok:* Yayında ✅")
            else:
                print(f"⚠️ TikTok API Uyarısı: {tt_res.get('error')}")
        except Exception as tte:
            print(f"⚠️ TikTok API Hatası: {tte}")

    # 2. Resmi API yoksa veya başarısız olduysa Web Tarayıcı Otomasyonunu dene (Split-Screen)
    if not any("TikTok" in s and "Yayında" in s for s in platforms_status):
        try:
            from app.publishers.tiktok_browser import has_active_tiktok_session, upload_via_tiktok_browser
            if has_active_tiktok_session():
                print("🌐 TikTok: Web tarayıcı oturumuyla (Split-Screen ASMR) yükleniyor...")
                tb_res = await asyncio.to_thread(
                    upload_via_tiktok_browser,
                    video_path=split_video_path,
                    title=title,
                    tags=tags,
                    headless=True,
                )
                if tb_res.get("status") == "success":
                    print(f"✅ TikTok (Web): Yayında")
                    platforms_status.append(f"🎵 *TikTok:* Yayında (Web) ✅")
                else:
                    print(f"⚠️ TikTok Web Uyarısı: {tb_res.get('error')}")
                    platforms_status.append(f"🎵 *TikTok:* ⚠️ {tb_res.get('error', '')[:40]}")
        except Exception as tbe:
            print(f"⚠️ TikTok Web Hatası: {tbe}")

    # Meta Threads
    if config.THREADS_USER_ID and config.THREADS_ACCESS_TOKEN:
        try:
            from app.publishers.threads import upload_to_threads
            threads_res = upload_to_threads(
                video_filename=res.get("video_filename", Path(video_path).name),
                caption=f"{title}\n\n{description}\n\n#DarkWealth #Shorts #Success",
                threads_user_id=config.THREADS_USER_ID,
                access_token=config.THREADS_ACCESS_TOKEN,
                tunnel_log_path=config.TUNNEL_LOG_PATH,
            )
            if threads_res.get("status") == "success":
                print(f"✅ Threads: Yayında (ID: {threads_res.get('post_id')})")
                platforms_status.append(f"🧵 *Threads:* Yayında ✅")
            else:
                print(f"⚠️ Threads Uyarısı: {threads_res.get('error')}")
                platforms_status.append(f"🧵 *Threads:* ⚠️ {threads_res.get('error', '')[:40]}")
        except Exception as the:
            print(f"⚠️ Threads Hatası: {the}")

    # X / Twitter (Video)
    if config.X_CLIENT_ID and config.X_REFRESH_TOKEN:
        try:
            from app.publishers.x import upload_video_to_x
            x_res = upload_video_to_x(
                video_path=video_path,
                text=f"{title}\n\n#DarkWealth #Shorts #Motivation",
                client_id=config.X_CLIENT_ID,
                client_secret=config.X_CLIENT_SECRET,
                refresh_token=config.X_REFRESH_TOKEN,
            )
            if x_res.get("status") == "success":
                print(f"✅ X (Video): Yayında (Tweet: {x_res.get('tweet_id')})")
                platforms_status.append(f"🐦 *X (Video):* Yayında ✅")
            else:
                print(f"⚠️ X Uyarısı: {x_res.get('error')}")
                platforms_status.append(f"🐦 *X (Video):* ⚠️ {x_res.get('error', '')[:40]}")
        except Exception as xe:
            print(f"⚠️ X Hatası: {xe}")

    # Pinterest (Video Pin)
    if config.PINTEREST_CLIENT_ID and config.PINTEREST_REFRESH_TOKEN and config.PINTEREST_BOARD_ID:
        try:
            from app.publishers.pinterest import upload_to_pinterest
            pin_res = upload_to_pinterest(
                video_path=video_path,
                title=title,
                description=description,
                client_id=config.PINTEREST_CLIENT_ID,
                client_secret=config.PINTEREST_CLIENT_SECRET,
                refresh_token=config.PINTEREST_REFRESH_TOKEN,
                board_id=config.PINTEREST_BOARD_ID,
            )
            if pin_res.get("status") == "success":
                print(f"✅ Pinterest: Yayında (Pin: {pin_res.get('pin_id')})")
                platforms_status.append(f"📌 *Pinterest Video Pin:* Yayında ✅")
            else:
                print(f"⚠️ Pinterest Uyarısı: {pin_res.get('error')}")
                platforms_status.append(f"📌 *Pinterest Video Pin:* ⚠️ {pin_res.get('error', '')[:40]}")
        except Exception as pe:
            print(f"⚠️ Pinterest Hatası: {pe}")

    # 3. Telegram Bildirimi
    print("\n📱 [3/3] Telegram Bildirimi Gönderiliyor...")
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        growth_extra = ""
        try:
            from app.channel_growth import analyze_channel_growth
            growth_info = analyze_channel_growth()
            if "channel" in growth_info:
                ch = growth_info["channel"]
                top = growth_info.get("top_performer")
                top_str = f"\n🔥 *En Çok İzlenen:* {top['title']} ({top['views']} izlenme)" if top else ""
                growth_extra = f"\n\n📈 *Kanal Nabzı:* {ch['total_views']} toplam izlenme | {ch['subscribers']} abone{top_str}"
        except Exception:
            pass

        platforms_summary = "\n".join(platforms_status)
        tg_text = (
            f"🎬 *Günün Viral Videosu Yayında! (Peak Motivation)*\n\n"
            f"📌 *Başlık:* {title}\n"
            f"🎯 *Konsept:* Dark Wealth & High-Stakes Business\n\n"
            f"{platforms_summary}"
            f"{growth_extra}\n\n"
            f"📊 *Kanal:* Peak Motivation (@peakmotivation-o4e)"
        )
        try:
            send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, tg_text)
            print("✅ Telegram mesajı başarıyla iletildi.")
        except Exception as te:
            print(f"⚠️ Telegram hatası: {te}")
            
    print("\n🎉 GÜNLÜK OTONOM İŞLEM TAMAMLANDI!")
    print(f"Canlı Video: {video_url}\n")
    return video_url


def run_scheduler_loop(target_hour: int = 18, target_minute: int = 30):
    print(f"🕒 Otonom Zamanlayıcı Devrede! Hedef Saat: Her gün {target_hour:02d}:{target_minute:02d} (TSİ)")
    print("Durdurmak için Ctrl + C tuşlarına basın.\n")
    
    last_run_day = None
    while True:
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        if (now.hour == target_hour and now.minute >= target_minute) and (last_run_day != today_str):
            try:
                asyncio.run(execute_daily_run())
                last_run_day = today_str
            except Exception as e:
                print(f"❌ Günlük çalıştırma hatası: {e}")
                
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Peak Motivation Otonom Günlük Yayın Motoru")
    parser.add_argument("--now", action="store_true", help="Zamanı beklemeden hemen 1 video üret ve yayınla")
    parser.add_argument("--trend", action="store_true", help="Canlı Google Trends'ten sıcak gündem konusu seç")
    parser.add_argument("--director", action="store_true", help="Telegram Yönetmen Modu: yayınlamadan önce onay butonları gönder")
    parser.add_argument("--hour", type=int, default=18, help="Yayın saati (varsayılan: 18)")
    parser.add_argument("--minute", type=int, default=30, help="Yayın dakikası (varsayılan: 30)")
    
    args = parser.parse_args()
    
    if args.now or args.trend or args.director:
        asyncio.run(execute_daily_run(use_trend=args.trend, director_mode=args.director))
    else:
        run_scheduler_loop(target_hour=args.hour, target_minute=args.minute)
