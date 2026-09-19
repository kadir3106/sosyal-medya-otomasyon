"""
TikTok Web Otomatik Yükleme Modülü (Playwright)

Resmi API onay süreçlerine ve kurumsal bürokrasiye gerek kalmadan,
kullanıcının yerel tarayıcı oturumu üzerinden TikTok Creator Center'a
1080p dikey videoları tam otomatik olarak yükler.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).resolve().parent.parent.parent.parent / "video-output" / "tiktok_session"
if not SESSION_DIR.parent.exists():
    SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "video-output" / "tiktok_session"


def has_active_tiktok_session() -> bool:
    """Yerel TikTok oturumunun bulunup bulunmadığını kontrol eder."""
    if not SESSION_DIR.exists():
        return False
    # Basitçe dizinin dolu olup olmadığına bak
    return any(SESSION_DIR.iterdir())


def upload_via_tiktok_browser(
    video_path: str,
    title: str,
    tags: list[str] | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Playwright ile TikTok Creator Center üzerinden videoyu yükler ve yayınlar."""
    if not has_active_tiktok_session():
        return {
            "platform": "tiktok",
            "status": "error",
            "error": "Aktif TikTok web oturumu bulunamadı. Lütfen 'python scripts/tiktok_browser_login.py' çalıştırarak bir kez giriş yapın.",
        }

    abs_video_path = str(Path(video_path).resolve())
    if not os.path.isfile(abs_video_path):
        return {
            "platform": "tiktok",
            "status": "error",
            "error": f"Video dosyası bulunamadı: {abs_video_path}",
        }

    # Açıklama ve etiketler
    tag_str = " ".join(f"#{t.lstrip('#')}" for t in (tags or ["Shorts", "DarkWealth", "Viral"]))
    caption = f"{title} {tag_str}".strip()

    try:
        with sync_playwright() as p:
            # Persistent context ile kayıtlı oturumu aç
            launch_kwargs = {
                "user_data_dir": str(SESSION_DIR),
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
                "no_viewport": True,
            }
            context = p.chromium.launch_persistent_context(**launch_kwargs)

            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(60000)

            logger.info("TikTok Creator Center Yükleme Sayfasına gidiliyor...")
            page.goto("https://www.tiktok.com/creator-center/upload", wait_until="domcontentloaded")
            time.sleep(3)

            # Giriş yapılmış mı doğrula
            if "login" in page.url:
                context.close()
                return {
                    "platform": "tiktok",
                    "status": "error",
                    "error": "TikTok oturumunun süresi dolmuş. Lütfen 'python scripts/tiktok_browser_login.py' ile tekrar giriş yapın.",
                }

            # Varsa eski taslak / yarım kalmış yükleme uyarısını temizle
            discard_btn = page.locator('button:has-text("Discard"), button:has-text("Vazgeç")')
            if discard_btn.count() and discard_btn.first.is_visible():
                logger.info("Önceki taslak uyarısı temizleniyor (Discard)...")
                discard_btn.first.click()
                time.sleep(2)
                confirm_discard = page.locator('div[class*="modal"] button:has-text("Discard"), div[class*="Modal"] button:has-text("Discard")')
                if confirm_discard.count() and confirm_discard.first.is_visible():
                    confirm_discard.first.click()
                    time.sleep(2)

            # iframe veya ana sayfadaki dosya seçiciyi bul
            logger.info("Video dosyası seçiciye iletiliyor...")
            try:
                page.wait_for_selector('input[type="file"]', timeout=25000)
            except Exception:
                pass

            upload_input = page.locator('input[type="file"]').first
            if not upload_input.count():
                for frame in page.frames:
                    frame_input = frame.locator('input[type="file"]').first
                    if frame_input.count():
                        upload_input = frame_input
                        break

            if not upload_input.count():
                context.close()
                return {
                    "platform": "tiktok",
                    "status": "error",
                    "error": "TikTok yükleme sayfasında video yükleme alanı bulunamadı.",
                }

            upload_input.set_input_files(abs_video_path)
            logger.info(f"Video yüklendi: {abs_video_path}. İşlenmesi bekleniyor...")

            # Varsa karşılama / tanıtım modal popup'larını kapat
            time.sleep(4)
            for _ in range(3):
                try:
                    page.keyboard.press("Escape")
                    dismiss_btn = page.locator('button:has-text("Got it"), button:has-text("Anladım"), button:has-text("Tamam"), button:has-text("Kapat"), div[class*="Modal"] button, div[class*="modal"] button').first
                    if dismiss_btn.is_visible():
                        dismiss_btn.click(timeout=1500, force=True)
                except Exception:
                    pass
                time.sleep(1)

            # Başlık ve açıklama alanını doldur
            caption_input = page.locator('div[contenteditable="true"]').first
            if caption_input.count():
                try:
                    caption_input.click(force=True, timeout=5000)
                except Exception:
                    page.keyboard.press("Escape")
                    caption_input.click(force=True, timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                caption_input.type(caption, delay=15)
                time.sleep(1)
                page.keyboard.press("Escape")  # Hashtag otomatik tamamlama kutucuğunu kapat
                logger.info(f"Açıklama girildi: {caption}")

            # Yüklemenin ve işlemenin bitmesini bekle (%100 veya 'Uploaded')
            logger.info("Yükleme tamamlanma sinyali bekleniyor...")

            # Gerçek 'Post' / 'Yayınla' butonunu bul (Sol menüdeki 'Posts' butonunu değil!)
            post_button = None
            for _ in range(100):  # 1080p videolar için ~5 dakikaya kadar bekle
                time.sleep(3)
                # Sayfayı alta kaydırarak alt bilgi çubuğunun DOM'da aktif kalmasını sağla
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                for btn in page.locator("button").all():
                    try:
                        txt = btn.inner_text().strip()
                        # 'Posts' menü butonunu dışla, sadece tam 'Post' veya 'Yayınla' ara
                        if txt in ("Post", "Yayınla") and btn.is_visible() and btn.is_enabled():
                            post_button = btn
                            break
                    except Exception:
                        pass

                if post_button:
                    break
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

            if post_button:
                post_button.click(force=True)
                logger.info("TikTok 'Yayınla' (Post) butonuna tıklandı.")
                time.sleep(10)
                context.close()
                return {
                    "platform": "tiktok",
                    "status": "success",
                    "detail": "Video TikTok Creator sayfasına web otomasyonuyla başarıyla yüklendi ve yayınlandı.",
                }

            context.close()
            return {
                "platform": "tiktok",
                "status": "error",
                "error": "TikTok 'Post' butonu aktifleşmedi veya süre aşımına uğradı.",
            }

    except Exception as exc:
        logger.exception("TikTok web yükleme hatası:")
        return {"platform": "tiktok", "status": "error", "error": str(exc)}
