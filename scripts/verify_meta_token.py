"""
Meta (Instagram Reels & Facebook) Token Doğrulama ve Teşhis Aracı
Kullanım:
    python scripts/verify_meta_token.py [YENI_TOKEN_OPSIYONEL]
"""

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
import requests


def check_token(token: str):
    print("=" * 60)
    print("🔍 META (INSTAGRAM & FACEBOOK) TOKEN KONTROLÜ")
    print("=" * 60 + "\n")

    if not token:
        print("❌ Token bulunamadı! .env dosyasında META_PAGE_ACCESS_TOKEN boş veya belirtilmedi.")
        return False

    # 1. Token debug / geçerlilik kontrolü
    url = "https://graph.facebook.com/v19.0/me"
    params = {"fields": "id,name", "access_token": token}
    r = requests.get(url, params=params)
    
    if r.status_code != 200:
        err = r.json().get("error", {})
        print(f"❌ Token Geçersiz veya Süresi Dolmuş:")
        print(f"   Hata Mesajı: {err.get('message')}")
        print(f"   Hata Kodu: {err.get('code')}")
        print("\n💡 NASIL YENİLENİR?")
        print("1. https://developers.facebook.com/tools/explorer/ adresine gidin.")
        print("2. 'User or Page' kısmından Facebook Sayfanızı seçin.")
        print("3. İzinler: 'pages_show_list', 'pages_read_engagement', 'instagram_basic', 'instagram_content_publish'.")
        print("4. 'Generate Access Token' butonuna basın.")
        print("5. Aldığınız token'ı .env içindeki META_PAGE_ACCESS_TOKEN değişkenine yapıştırın.")
        return False

    page_data = r.json()
    print(f"✅ Sayfa Bağlantısı Başarılı: {page_data.get('name')} (ID: {page_data.get('id')})")

    # 2. Bağlı Instagram Business hesabını kontrol et
    accounts_url = f"https://graph.facebook.com/v19.0/{page_data.get('id')}"
    r_ig = requests.get(accounts_url, params={"fields": "instagram_business_account{id,username}", "access_token": token})
    ig_data = r_ig.json().get("instagram_business_account")
    
    if ig_data:
        print(f"✅ Bağlı Instagram Hesabı: @{ig_data.get('username')} (ID: {ig_data.get('id')})")
        print("\n🎉 Tebrikler! Meta entegrasyonu tamamen aktif. Instagram Reels yüklemeleri yapılabilir.")
        return True
    else:
        print("\n⚠️ Sayfaya bağlı bir Instagram Profesyonel/İşletme hesabı bulunamadı.")
        print("Instagram hesabınızı Facebook sayfanıza bağladığınızdan emin olun.")
        return False


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else config.META_PAGE_ACCESS_TOKEN
    check_token(t)
