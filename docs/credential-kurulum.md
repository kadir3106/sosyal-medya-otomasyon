# 🔑 Credential Kurulum Rehberi

Bu rehber, sistemin **kendi İngilizce kanalını** büyütmesi için gereken tüm
anahtarları alma sürecini anlatır. Her anahtar alındıktan sonra `.env`
dosyasına yazılır ve `docker compose up -d --force-recreate video-worker`
ile sisteme tanıtılır.

> Not: Sistem anahtarsız da video üretebilir (animasyonlu fallback ile) —
> aşağıdaki anahtarlar onu GÜÇLENDİRİR: gerçek stok görüntü (Pexels),
> otomatik yayın (platformlar), günlük onay döngüsü (Telegram).

## Öncelik Sırası

| # | Anahtar | Süre | Neyi açar |
|---|---|---|---|
| 1 | **Telegram** (token + chat_id) | 10 dk | Günlük otomasyon döngüsü (onay butonları) |
| 2 | **Pexels** | 5 dk | Gerçek stok video klipleri |
| 3 | **YouTube** (OAuth) | 30-60 dk | Kendi kanalına Shorts yükleme |
| 4 | **X** (OAuth 2.0) | 30 dk | Görsel kartları tweet olarak atma |
| 5 | **Meta** (IG + FB) | 30-60 dk | Instagram + Facebook Reels |
| 6 | **LinkedIn** (OAuth) | 30 dk + onay | Görsel kartları LinkedIn'e atma |
| 7 | **TikTok** (Developer app) | kayıt hızlı, **audit günler/haftalar** | TikTok'a yükleme — **EN ERKEN BAŞVURULMALI** |

---

## 1. Telegram (10 dk)

1. Telegram'da **@BotFather**'a yaz → `/newbot` → isim ver → token'ı kopyala
2. `.env` → `TELEGRAM_BOT_TOKEN=<token>`
3. Bot'a `/start` mesajı gönder
4. `python scripts/get_chat_id.py` → çıkan sayıyı `.env` → `TELEGRAM_CHAT_ID=`
5. `docker compose up -d --build video-worker && docker compose restart n8n` ve `python scripts/setup_n8n.py`

> Onay butonlarına basınca ne olduğunu `video-worker`'ın kendisi karşılıyor
> (Telegram long-polling ile) — n8n'de ayrıca bir "Approval Handler" workflow'u
> yok. `docker compose logs video-worker | grep telegram_bot` ile dinleyicinin
> çalıştığını doğrulayabilirsin.

## 2. Pexels (5 dk)

1. https://www.pexels.com/api/ → hesap aç → API key anında verilir
2. `.env` → `PEXELS_API_KEY=<key>`
3. `docker compose up -d --force-recreate video-worker`

## 3. YouTube (30-60 dk)

1. https://console.cloud.google.com → proje oluştur → **YouTube Data API v3** → Enable
2. **OAuth consent screen**: External → uygulama adı + e-postalar → Scopes:
   `youtube.upload`, `youtube.readonly` → Test users'a kendi hesabını ekle
3. **Credentials → OAuth client ID** → Application type: **Desktop app**
   → `YOUTUBE_CLIENT_ID` ve `YOUTUBE_CLIENT_SECRET`'ı `.env`'e yaz
4. Refresh token'ı script ile al:
   ```
   python scripts/youtube_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>
   ```
   → çıkan `YOUTUBE_REFRESH_TOKEN`'ı `.env`'e yaz
5. ⚠️ Consent screen "Testing" durumundayken refresh token **7 gün** sonra ölür.
   App'i **verification**'a gönder; onaylanana kadar haftada bir script'i tekrar çalıştır.

## 4. X / Twitter (30 dk)

1. https://developer.x.com → Proje oluştur → **X API v2** (ücretsiz katman yeterli)
2. App oluştur → **User authentication settings**:
   - App permissions: **Read and write**
   - Type of App: **Web App**
   - Callback URI: `http://localhost:8098/callback`
3. Keys sekmesinden `X_CLIENT_ID` ve `X_CLIENT_SECRET`'ı `.env`'e yaz
4. Refresh token'ı script ile al:
   ```
   python scripts/x_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>
   ```
   → `X_REFRESH_TOKEN`'ı `.env`'e yaz
5. ⚠️ Bearer Token İŞE YARAMAZ (sadece okuma) — post atmak için bu OAuth 2.0
   user-context akışı şart. Ücretsiz katman ayda ~1500 tweet atmana izin verir.

## 5. Meta / Instagram + Facebook (30-60 dk)

1. https://developers.facebook.com → app oluştur (Business)
2. Ürünler: **Instagram** (Instagram Basic Display değil, **Instagram API**) ekle
3. **Facebook Login for Business** ekle
4. Instagram Business hesabını Facebook sayfana bağla (kendi hesapların yeterli)
5. **Graph API Explorer** ile `me/accounts` → sayfanın `id` ve **Page Access Token**'ını al
   → `.env`: `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN`
6. `{page-id}?fields=instagram_business_account` → IG account id
   → `.env`: `META_IG_USER_ID=`
7. ⚠️ Development modunda kendi hesabına yükleme yapabilirsin (review gerekmez);
   müşteri hesaplarına yüklemek için app review gerekir.

## 6. LinkedIn (30 dk + onay bekleme)

1. https://developer.linkedin.com → app oluştur
2. **Products → "Share on LinkedIn"** ekle (**onay sürebilir — en erken başvur**)
3. **Auth**: OAuth 2.0 scopes → `openid profile email w_member_social`
   Redirect URLs → `http://localhost:8098/callback`
4. `LINKEDIN_CLIENT_ID` + `LINKEDIN_CLIENT_SECRET`'ı `.env`'e yaz
5. Script ile token + author URN al:
   ```
   python scripts/linkedin_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>
   ```
   → `LINKEDIN_REFRESH_TOKEN` ve `LINKEDIN_AUTHOR_URN`'ı `.env`'e yaz

## 7. TikTok (kayıt 30 dk, audit GÜNLER/HAFTALAR)

1. https://developers.tiktok.com → giriş yap → **Manage apps** → **Connect an app**
   - Platform: **Web**
   - Redirect URI: `http://localhost:8098/callback`
   - Gizlilik politikası + kullanım şartları URL'i isteyebilir (statik bir HTML
     sayfası yeterli — barındıracak yerin yoksa GitHub Pages kullanılabilir)
2. App'e **Content Posting API** ürününü ekle, `video.publish` + `video.upload`
   scope'larını iste
3. "Basic Information" sekmesinden `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET`'ı
   `.env`'e yaz
4. Refresh token'ı al ve `video-worker` container'ına otomatik yazdır:
   ```
   python scripts/tiktok_oauth_helper.py <CLIENT_KEY> <CLIENT_SECRET>
   ```
   (video-worker'ın `docker compose up -d` ile ayakta olması gerekir — script
   token'ı doğrudan `/data/tiktok-token/token.json`'a yazar, `.env`'e eklenecek
   bir şey yok)
5. **Audit başvurusunu aynı gün yap** (en uzun süren adım) — app detayında
   "Submit for review", kullanım amacını net yaz (örn. "kişisel/işletme sosyal
   medya otomasyon sistemi — günlük üretilen videoları hesaba yüklüyor")
6. Audit onaylanana kadar videolar `privacy_level=SELF_ONLY` (private) yüklenir —
   kod bunu otomatik yönetir; onay gelince `.env`'de `TIKTOK_AUDITED=true` yap.

---

## Hepsini Aldıktan Sonra

```powershell
docker compose up -d --force-recreate video-worker
docker compose restart n8n
python scripts/setup_n8n.py
```

Durum kontrolü: `docker compose ps` — dört servis Up olmalı (n8n, video-worker, media-gateway, cloudflared).
Test: `python scripts/setup_n8n.py` çıktısında 3 workflow "AKTİF" yazmalı (Daily Video Pipeline, Daily Image Pipeline, Weekly Analytics Report).
