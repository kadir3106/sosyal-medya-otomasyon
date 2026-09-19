"""
TikTok Web Tarayıcı Giriş ve Oturum Saklama Aracı

Bu araç, resmi TikTok API evraklarıyla/onaylarıyla uğraşmadan
Playwright persistent context ile TikTok'a tek seferlik giriş yapmanızı
ve oturumu yerel profil olarak kaydetmenizi sağlar.
"""

import os
import sys
import time
from pathlib import Path

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

SESSION_DIR = Path(__file__).resolve().parent.parent / "video-output" / "tiktok_session"


def setup_tiktok_session():
    print("=" * 60)
    print("🚀 TIKTOK KALICI OTURUM KURULUMU")
    print("=" * 60)
    print("\n1. Tarayıcı (Chromium/Chrome) açılıyor...")
    print("2. Açılan pencerede TikTok hesabınıza giriş yapın (QR kod, şifre vb.).")
    print("3. Giriş yaptıktan sonra tarayıcıyı kapatmayın, sistem otomatik algılayacaktır.\n")

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("🌐 Chromium tarayıcı penceresi açılıyor...", flush=True)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )

        page = context.pages[0] if context.pages else context.new_page()
        print("🌐 Tarayıcı hazır! TikTok giriş sayfası açılıyor...", flush=True)
        try:
            page.goto("https://www.tiktok.com/login", timeout=45000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Bilgi: Sayfa yönlendirme uyarısı: {e}. Devam ediliyor...", flush=True)

        print("⏳ TikTok girişinizin tamamlanması bekleniyor (Maksimum 5 dakika)...")
        print("İpucu: Giriş yaptıktan sonra TikTok ana sayfasına veya yükleme merkezine geçiş yapın.\n")

        logged_in = False
        start_time = time.time()

        while time.time() - start_time < 300:
            current_url = page.url
            # Giriş yapıldığında login sayfası dışına çıkar veya çerezler oluşur
            cookies = context.cookies()
            has_session = any(c.get("name") in ("sessionid", "sessionid_ss", "sid_tt") for c in cookies)

            if has_session or ("login" not in current_url and "tiktok.com" in current_url):
                # 3 saniye bekle ve çerezlerin tam oturduğunu doğrula
                time.sleep(3)
                print("🎉 TEBRİKLER! TikTok oturumu başarıyla algılandı ve kaydedildi.", flush=True)
                print(f"📁 Oturum Dizini: {SESSION_DIR}", flush=True)
                print("\nArtık render edilen her video TikTok Creator sayfasına otomatik yüklenecektir!", flush=True)
                logged_in = True
                break

            time.sleep(2)

        if not logged_in:
            print("\n⚠️ Süre doldu veya giriş algılanamadı. Tekrar denemek için komutu yeniden çalıştırın.", flush=True)

        context.close()


if __name__ == "__main__":
    setup_tiktok_session()
