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

## Otonom yayın: iki yetki, ikisi de bilinçli

`scripts/daily_autonomous_agent.py` günde bir video üretir ve varsayılan olarak **hiçbir platforma göndermez**. Yayın için iki bağımsız yetkiden biri gerekir:

| Yetki | Nasıl açılır | Ne zaman kullanılır |
| --- | --- | --- |
| İnsan onayı | `--director` (Telegram'da "Yayınla" butonu) | Önerilen varsayılan. `scripts/run_daily.bat` bu modu kullanır. |
| Makine onayı | `.env`: `ALLOW_AUTONOMOUS_PUBLISH=true` | Onaysız, tam otonom akış. YouTube'a `public` yükler; geri alınamaz. |

**Yalnızca tam olarak `true` sayılır.** Kod `...lower() == "true"` ile karşılaştırdığı için `1`, `yes`, `on`, `TRUE ` (sondaki boşluk) ve `True!` **kapalı** sayılır — yazım hatası kazara public yayın başlatmasın diye. Bu davranış `test_publish_gate_blocks_lookalike_values` ile kilitli.

`--director` modunda akış: video üretilir → Telegram'a önizleme + iki buton gider → "Yayınla" yayınlar, "İptal" her zaman kazanır (açık bayrağı bile ezer), 180 saniye yanıt gelmezse tur **yayınlamadan biter** (bayrak açıksa otomatik yayınlar — onay mesajı hangisinin olacağını önceden söyler).

> ⚠️ Bu bayrak daha önce yalnızca kodda vardı; `.env.example`'da tanımlı olmadığı için pratikte hiçbir kurulum onu açamıyordu ve `run_daily.bat` onay adımını atlayarak (`--now`) çalıştığı için günlük tur video üretip sessizce yayınlamadan bitiyordu.

## Sızıntı temizliği

Geçmişte commit edilmiş bir TikTok tarayıcı oturumu ve bir n8n yedek arşivi var. **Döndürme (rotation) adımları ve `git filter-repo` komutları:** [`docs/SIZINTI_TEMIZLIGI.md`](docs/SIZINTI_TEMIZLIGI.md). Bu işlemler yıkıcıdır, sırayla ve elle koşulmalıdır.

## Security note (credential rotation)

`main` previously tracked a Playwright TikTok browser profile under `video-output/tiktok_session/` (1015 files across 2 commits). Those paths are now gitignored and untracked on this branch, but **the TikTok session/cookies that lived there are still valid credentials** — revoke them from TikTok (log out all sessions) and re-run `scripts/refresh_tiktok_session.py`.

Measured scope of the leak (2026-11-02): two real items. **`video-output/tiktok_session/`** (1015 files, 2 commits) and **`backups/otomasyon-yedek-2026-09-05.tar.gz`** (a full backup tarball — its contents are unknown, so treat every secret that existed on 2026-09-05 as exposed). `.env` itself was never committed (covered by `.gitignore:2`), and 8 of the 14 `scripts/secret_scan_baseline.json` entries are fake values from `tests/test_secret_scan*.py` fixtures. History rewrite (`git filter-repo`) is optional; rotation is not.

> The scanner now **opens** committed archives (`.zip`, `.tar.gz`, …) instead of skipping binary blobs — the tarball above was invisible to it until 2026-11-02. It also flags every archive path as a finding on its own, so an archive it cannot open is never reported as "clean".

## TikTok yayını: iki yol

**1) Resmi API (varsayılan, ek kurulum yok).** `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` + `tiktok-token` volume'undaki token dosyası. Yalnızca `requests` kullanır, playwright gerektirmez.

> ⚠️ `TIKTOK_AUDITED=false` iken API **`SELF_ONLY`** (özel taslak) yayınlar; public yayın için uygulamanın audited olması ve bu bayrağın `true` yapılması gerekir.

**2) Web (Playwright) — opt-in.** Varsayılan imajda **kapalı** (≈400 MB ekler). Public yayın için API audited değilse bu yol gerekir.

```bash
# İmajı tarayıcı desteğiyle derle
docker compose build --build-arg INSTALL_BROWSER=1 video-worker

# Bir kez görünür tarayıcıyla giriş yap (headless olmaz)
python scripts/tiktok_browser_login.py

# Oturumu konteyner volume'una aktar ve doğrula
python scripts/refresh_tiktok_session.py --upload
python scripts/refresh_tiktok_session.py --verify

docker compose up -d video-worker
```

Açılmazsa ne olur: uygulama sorunsuz çalışır; TikTok web adımı atlanır ve Telegram özetinde **"Yayın yok (playwright imajda kurulu değil)"** satırı görünür. Sessizce yutulmaz.

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
