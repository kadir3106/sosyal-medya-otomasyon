# Sosyal Medya Video Otomasyon Sistemi

Kurulum ve mimari için bkz. `docs/superpowers/specs/2026-09-03-sosyal-medya-video-otomasyon-design.md`.
Uygulama planı: `docs/superpowers/plans/2026-09-03-sosyal-medya-video-otomasyon.md`.

## Render stack

- **Daily path (production):** Python + **FFmpeg** in `video-worker/` (`app/pipeline.py` → `render.py` / `split_screen.py`), scheduled by n8n → Telegram approval → `/publish`.
- **Remotion (`remotion-pipeline/`):** **experimental / host-only.** Not in `docker-compose.yml`. Use `/render-remotion` only for experiments; do not rely on it for the daily cron.

## Geliştirme

Testleri çalıştırmak için:
```bash
docker compose build video-worker
docker compose run --rm video-worker pytest tests/ -v
```

Or locally (from `video-worker/`):
```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tüm sistemi ayağa kaldırmak için `.env` dosyasını `.env.example`'dan kopyalayıp doldurun, sonra:
```bash
docker compose up -d
```
n8n arayüzü: http://localhost:5678

## Security note (credential rotation)

`main` previously tracked a Playwright TikTok browser profile under `video-output/tiktok_session/` and a backup tarball. Those paths are now gitignored and untracked on this branch, but **anything that was ever public should be rotated**: TikTok session/cookies, TikTok PKCE/OAuth tokens, and any secrets that may have lived inside `backups/*.tar.gz`. History rewrite is optional; rotation is not.

## n8n Workflow Kurulumu (tek komut)

Workflow'lar `n8n-workflows/` klasöründe versiyon kontrolü altında tutulur ve API üzerinden kurulur:

```powershell
python scripts/setup_n8n.py
```

Script şunları yapar:
1. n8n owner hesabını kurar — e-posta `.env` içinden `N8N_EMAIL` ile değiştirilebilir (varsayılan: `admin@local.dev`). Şifre ilk kurulumda **rastgele üretilip `.env`'e `N8N_PASSWORD` olarak kaydedilir**; kendin belirlemek istersen `.env`'e önceden `N8N_PASSWORD=...` yaz.
2. `TELEGRAM_BOT_TOKEN` doluysa `Telegram - Otomasyon Bot` credential'ını oluşturur (sadece mesaj/video/görsel *gönderimi* için — onay butonlarını dinlemek için değil, bkz. aşağıdaki not)
3. 3 workflow'u import eder ve aktive eder:
   - **Daily Video Pipeline** — Cron (her gün 09:00) → `/generate` → Telegram'a video + onay butonları
   - **Daily Image Pipeline** — Cron (her gün 12:00) → `/generate-image` → Telegram'a görsel kart + onay butonları (X + LinkedIn yayını)
   - **Weekly Analytics Report** — Cron (Pazartesi 10:00) → `/analytics/weekly` → Telegram raporu

> **Onay butonları neden n8n'de değil:** n8n'in Telegram Trigger düğümü, callback'leri dinlemek için Telegram'a `setWebhook` ile *public* bir HTTPS adres bildirmek zorunda. Bu kurulumda n8n'e giden bir tünel yok (bilinçli — n8n'in kendisini internete açmak istemiyoruz), bu yüzden bu düğüm hiçbir zaman aktive olamıyordu. Onay/red/tekrar-dene işleyişi bunun yerine `video-worker` içinde, `app/telegram_bot.py`'de, Telegram'ın `getUpdates` long-polling API'siyle çalışıyor — public adres gerektirmiyor. `video-worker` konteyneri ayakta olduğu sürece bu dinleyici arka planda çalışır; `docker compose logs video-worker` içinde `[telegram_bot] Onay dinleyici başladı` satırını görürsün.

> Güvenlik: n8n ve video-worker portları yalnızca `127.0.0.1`'e bağlıdır (aynı ağdaki cihazlardan erişilemez). LAN'dan erişim gerekirse `docker-compose.yml` içindeki port bağlamalarını bilinçli olarak değiştir. İnternete açılan tek yüzey Cloudflare tüneli — o da doğrudan `video-worker`'a değil, önündeki `media-gateway` (Caddy) servisine bağlı ve yalnızca `GET /media/*` isteklerini geçirir (bkz. `caddy/Caddyfile`). Instagram Reels yayını bu public URL'e ihtiyaç duyduğu için tünel kapatılamıyor, ama artık `/publish`, `/generate`, `/cleanup` gibi uçlar dışarıdan hiç görünmüyor.

## Telegram Kurulumu

1. `.env` içine `TELEGRAM_BOT_TOKEN` değerini yaz (BotFather'dan)
2. Bot'a `/start` mesajı gönder
3. Chat ID'yi bul: `python scripts/get_chat_id.py`
4. `.env` içine `TELEGRAM_CHAT_ID` yaz
5. `docker compose up -d --build` (video-worker'ın onay dinleyicisi `TELEGRAM_CHAT_ID` olmadan başlamaz)
6. `python scripts/setup_n8n.py` tekrar çalıştır (credential + workflow aktivasyonu için)

## Credential Durumu

| Anahtar | Gerekli | Durum |
|---|---|---|
| OPENROUTER_API_KEY | ✅ zorunlu (script üretimi) | `.env` içine yaz |
| TELEGRAM_BOT_TOKEN / CHAT_ID | ✅ onay akışı | `.env` içine yaz |
| PEXELS_API_KEY | ✅ stok klip | `.env` içine yaz |
| YOUTUBE_API_KEY | 📊 arama/istatistik (Data API v3) | upload yapmaz |
| YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN | YouTube Shorts upload | OAuth |
| TIKTOK_CLIENT_KEY/SECRET | TikTok upload | audit sonrası |
| META_IG_USER_ID / META_PAGE_ID / META_PAGE_ACCESS_TOKEN | IG/FB Reels upload | |
