# Sosyal Medya Otomasyon — Denetim ve Mükemmellik Planı

**Tarih:** 2026-09-05
**Denetlenen sürüm:** `8211bce` (master, 5 takipsiz/değişmiş dosyayla)
**Yöntem:** Canlı sistem üzerinde — çalışan container'lara istek atılarak, n8n log'ları okunarak, test paketi çalıştırılarak.

---

## Özet

| Ölçüt | Değer |
|---|---|
| Test | 92 / 92 geçiyor |
| Container | 3 / 3 ayakta (10–21 saattir) |
| Plan görevi | 20 / 24 tamam |
| Yayınlanmış içerik | **0** |
| Bağlı platform | **0 / 5** |
| Kod | 14 modül, 2.447 satır Python |

Mimari sağlam ve kod kalitesi iyi. Sistem her gün içerik üretebiliyor ama **bugüne kadar
tek bir gönderi yayınlamadı**. Zincir iki noktada kopuk: onayın geri dönmesi (K2) ve
yayın kimlik bilgileri (K3). Ayrıca aktif bir güvenlik açığı var (K1).

### Akış — nerede kopuyor

```
Cron 09:00 → /generate → Telegram (video+butonlar) → ✕ onay callback → ✕ /publish → 5 platform
   OK           OK              OK                     K2: aktive          K3: kimlik
                                                       edilemiyor          yok
```

---

## Bulgular

### K1 — Cloudflare tüneli tüm API'yi internete açıyor · KRİTİK / GÜVENLİK

`cloudflared tunnel --url http://video-worker:8000` sadece `/media` rotasını değil,
servisin tamamını dışarı veriyor. Dışarıdan doğrulandı:

```
GET https://<tünel>.trycloudflare.com/health  ->  200  {"status":"ok"}
GET https://<tünel>.trycloudflare.com/docs    ->  200  (OpenAPI arayüzü)
```

`/docs` açık olduğu için saldırı yüzeyi kendini belgeliyor. Adresi öğrenen biri
`POST /publish` ile senin hesaplarına içerik bastırabilir, `DELETE /cleanup/{dosya}`
ile medya silebilir, `POST /generate` ile OpenRouter kotanı yakabilir. Adres rastgele
ama gizli değil — Instagram'a `video_url` olarak gönderiliyor ve log'da düz metin duruyor.

**Çözüm:** Tünelin önüne yalnızca `GET /media/*` geçiren bir Caddy/nginx koy;
`video-worker`'ı doğrudan tünelden çek. Ek olarak
`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` ve yazma uçlarına
paylaşılan sırlı başlık kontrolü.

### K2 — Onay döngüsü ölü · KRİTİK / İŞLEVSEL

```
setup_out.txt:  [uyarı] Approval Handler aktive edilemedi: 400
n8n log:        Rolled back partial activation of workflow "vHWFRi15IVnpI6BE" (x5)
```

Kök neden: n8n'in `telegramTrigger` düğümü Telegram'a `setWebhook` çağırır, bunun için
public HTTPS adresi gerekir. `docker-compose.yml` içinde `WEBHOOK_URL`/`N8N_HOST` yok ve
n8n'e giden bir tünel yok — Telegram `localhost:5678` adresine ulaşamıyor. Sonuç: butona
basılıyor, hiçbir şey olmuyor, `pending.json` takılı kalıyor, ertesi gün `409`.

**Çözüm (önerilen):** n8n'i ikinci bir tünelle açmak yerine onayı video-worker'a taşı —
Telegram `getUpdates` ile long-polling yapan bir arka plan görevi. Public adres
gerektirmez, K1'i büyütmez, pytest'lenebilir.

### K3 — Hiçbir yayın kimlik bilgisi girilmemiş · KRİTİK / BLOKER

```
YOUTUBE_CLIENT_ID / SECRET / REFRESH_TOKEN   boş
TIKTOK_CLIENT_KEY / SECRET                   boş
META_IG_USER_ID / PAGE_ID / ACCESS_TOKEN     boş
X_CLIENT_ID / SECRET / REFRESH_TOKEN         boş
LINKEDIN_CLIENT_ID / SECRET / ...            boş
/data/media/published_log.json               yok  ->  hiç yayın olmamış
```

Elde olan `YOUTUBE_API_KEY` sadece arama/istatistik içindir, **video yükleyemez**.
Plan'daki Task 21–23 adım adım yazılı, `scripts/` altında OAuth helper'ları hazır.
TikTok audit onayı haftalar sürebilir — bugün başlat.

### K4 — `/publish` her şey başarısız olsa da 200 döner ve videoyu siler · YÜKSEK

`app/main.py:199-210` sonuçları toplar, log'a yazar, sonra medyayı ve `pending.json`
dosyasını **koşulsuz** siler. Beş platformun beşi de hata verse n8n `200 OK` görür ve o
günün videosu diskten silinmiştir. Yeniden deneme imkânı yok.

**Çözüm:** En az bir platform başarılıysa temizle. Hepsi başarısızsa `502` dön, dosyayı
`/data/media/failed/` altına taşı, Telegram'a "Tekrar dene" butonu gönder.

### K5 — 26 dış HTTP çağrısının hiçbirinde retry yok · YÜKSEK

OpenRouter, Pexels, YouTube, TikTok, Meta, X, LinkedIn — hepsi çıplak `requests`.
Tek bir `429`/`503` o günün içeriğini kaybettirir; ücretsiz OpenRouter modellerinde
429 rutindir.

**Çözüm:** Ortak `app/http.py` — `requests.Session` + `urllib3.Retry` (üstel backoff,
429/5xx, `Retry-After`). Sadece idempotent adımlar tekrarlanmalı: **TikTok token
yenileme asla tekrarlanmamalı** (refresh token rotasyona uğruyor).

### K6 — Uygulamada tek satır log yok · YÜKSEK / GÖZLEMLENEBİLİRLİK

```
grep -rn "import logging|logger\.|logging\." app/   ->  0 eşleşme
```

Hangi konu seçildi, LLM ne döndürdü, kaç klip indi, render ne sürdü, hangi platform
neden reddetti — hiçbiri kayıtlı değil.

**Çözüm:** `job_id` korelasyonlu JSON log, aşama süreleri, Telegram'a günlük özet.

### K7 — Görüntüler anlatımla ilgisiz · YÜKSEK / İÇERİK KALİTESİ

`extract_keywords` script'in ilk 5 uzun kelimesini alıyor; her kelime için Pexels'e
`per_page=1` ile sorgu atılıp **hep ilk sonuç** indiriliyor. 4 klip anlatım ritmine
bakılmadan döngüye alınıp sert kesmelerle birleştiriliyor.

**Çözüm:** LLM'den script ile *birlikte* sahne planı iste (cümle başına görsel sorgusu).
Sahne süresini o cümlenin TTS süresine bağla. `per_page=15` içinden rastgele seç.
Ken Burns yakınlaştırma + crossfade.

### K8 — Tek yuvalı `pending.json` · ORTA / ÖLÇEKLENME

09:00 videosu onaylanmadıysa 12:00 görsel hattı `409` alıp o günü atlıyor. Günde birden
fazla gönderi veya birden fazla marka mümkün değil.

**Çözüm:** İş başına `pending_<job_id>.json` ya da küçük bir SQLite iş tablosu;
`/media` yetkilendirmesi `job_id` üzerinden.

### K9 — X ve LinkedIn haftalık raporda yok · ORTA

Görsel hattı X + LinkedIn'e yayın yapıyor, `app/analytics.py` sadece
youtube/instagram/facebook/tiktok biliyor. Üretilen içeriğin yarısı kör noktada.

### K10 — Türkçe modda görsel arama sessizce çöküyor · ORTA

`_STOPWORDS` yalnızca İngilizce. `VIDEO_LANG=tr` iken "bir", "daha", "kadar" Pexels'e
sorgu olarak gidiyor, sonuç dönmüyor, sistem sessizce gradient fallback'e düşüyor.
Müşteriye satılacak mod tam olarak bu.

**Çözüm:** Türkçe stopword listesi + görsel sorgularını her zaman İngilizce üret
(K7'deki sahne planı bunu zaten çözer).

### K11 — Konu havuzu 50 maddede kilitli ve sırası sabit · ORTA

`select_next_topic` her zaman `remaining[0]` seçiyor; havuz bitince aynı 50 konu aynı
sırayla baştan başlıyor. 50 gün sonra kanal kendini tekrar ediyor. Performans verisi konu
seçimini hiç etkilemiyor.

### K12 — Prodüksiyon katmanı eksik · ORTA / İÇERİK KALİTESİ

Hook yok, arka plan müziği ve ducking yok, kapak görseli üretilmiyor, altyazı statik
(karaoke vurgusu yok), marka bumper'ı yok, başlık/açıklama beş platforma da aynı metin.

### K13 — İşletim boşlukları · ORTA

- PC 09:00'da kapalıysa o gün sessizce kayboluyor — kaçan cron telafisi yok
- `docker-compose.yml` içinde healthcheck yok, `depends_on` koşulsuz
- n8n log'unda `Last session crashed`
- `n8n-data`, `used_topics.json`, `published_log.json` yedeklenmiyor
- `setup_out.txt` n8n şifresini düz metin tutuyor ve `.gitignore` içinde değil

### K14 — Telegram bot token'ı dışarıdan da dinleniyor · KRİTİK / YENİ (2026-09-05)

Faz 0'da `app/telegram_bot.py` devreye alındıktan sonra sürekli `409 Conflict`
hatası gözlendi (`docker compose logs video-worker`). Telegram'ın `getUpdates`
API'si "tek seferde tek dinleyici" kuralı uyguluyor — bu hata, aynı bot
token'ının **bu makinenin dışında bir yerden** hâlâ aktif olarak dinlendiğini
gösteriyor. Ekarte edilenler: n8n webhook'u boş (`getWebhookInfo` → `url:""`),
bu makinede rakip container/process yok (`docker ps -a`, `tasklist` kontrol
edildi), token diğer yerel projelerde (MİKO, BorsaProjem) geçmiyor.

**Kullanıcı eylemi gerekiyor** — muhtemelen unutulmuş bir entegrasyon, açık
kalmış bir tarayıcı sekmesi/API test aracı, ya da başka bir otomasyon bu
token'ı kullanıyor. En hızlı ve kesin çözüm: BotFather → `/mybots` → botu seç
→ API Token → **Revoke current token**, yeni token'ı `.env`'e yaz,
`docker compose up -d --build video-worker` çalıştır. Bu, diğer tüketiciyi
anında keser ve K2'nin güvenilir çalışmasını sağlar.

---

## Yol haritası

Fazlar sıralı: kimlik bilgileri gelmeden dayanıklılığın ölçeceği bir şey yok, içerik
yayınlanmadan kaliteye yatırım anlamsız. Tek istisna TikTok audit — bugün başlamalı.

### Faz 0 — Kanamayı durdur (bugün, ~3 saat) → K1, K2, K4, K13 — ✅ TAMAMLANDI (2026-09-05)

- [x] Tünelin önüne yalnızca `GET /media/*` geçiren Caddy koy; `/docs`, `/redoc`, `/openapi.json` kapat
      — canlıda doğrulandı (tünelden `/health`/`/docs`/`/generate` 404, `/media/*` proxy'leniyor)
- [x] Onayı `telegramTrigger` yerine video-worker'da `getUpdates` long-polling'e taşı; Approval Handler'ı emekli et
      — `app/telegram_bot.py`; n8n'deki eski kayıt hem dosyadan hem canlı veritabanından silindi
- [x] `/publish`: hepsi başarısızsa `502`, dosyayı `failed/` altına taşı, Telegram'a "Tekrar dene"
      — test: `test_publish_returns_502_and_preserves_file_when_all_platforms_fail`
- [x] `setup_out.txt`/`setup_err.txt` sil, `.gitignore` ekle
- [x] Takipsiz debug script'lerini temizle (`_tg_trigger.js`, `scripts/_debug_*.py`)

**Yeni bulgu (K14) — bu fazda ortaya çıktı:** Telegram bot token'ı bu makinenin
dışında bir yerden hâlâ `getUpdates` ile dinleniyor; onay dinleyicisi sürekli
`409 Conflict` alıyor. Kaynağı bulunamadı (n8n webhook boş, bu makinede rakip
process/container yok, token diğer projelerde geçmiyor). **Kullanıcı eylemi
gerekiyor** — bkz. aşağıdaki "Sıradaki adımlar".

### Faz 1 — Gerçekten yayına çık (bu hafta; dış onaylar haftalar) → K3

- [ ] **TikTok audit başvurusu — ilk iş** (Task 22)
- [ ] YouTube OAuth + *aynı gün* verification başvurusu (Task 21 — test modunda token 7 günde ölüyor)
- [ ] Meta app + Instagram Business bağlantısı (Task 23)
- [ ] X ve LinkedIn OAuth (`scripts/x_oauth_helper.py`, `scripts/linkedin_oauth_helper.py`)
- [ ] Uçtan uca duman testi (Task 24)

### Faz 2 — Her gün çalışsın (2. hafta, ~2 gün) → K5, K6, K13 — neredeyse tamamlandı (2026-09-05)

- [x] Ortak `app/http_client.py`: Session + üstel backoff + `Retry-After` (429/500/502/503/504, total=3)
      — script_gen, image_gen, stock_media, analytics, x, linkedin, youtube, meta publisher'larına uygulandı.
      TikTok kasıtlı olarak dışarıda bırakıldı: refresh token her kullanımda rotasyona uğruyor,
      bir retry sunucuda başarıyla işlenmiş ama yanıtı kaybolmuş bir isteği artık geçersiz
      token'la tekrarlayıp hesabı kilitleyebilir (mevcut kod yorumundaki gerekçeyle aynı).
- [x] `job_id` korelasyonlu JSON log (`app/joblog.py`) — konu seçimi, script/TTS/klip/render süreleri,
      her platformun publish sonucu artık `docker compose logs video-worker`'da tek satır JSON olarak görünüyor.
      ⏳ Telegram'a günlük özet (ayrı bir digest mesajı) HENÜZ YOK — istenirse ayrı görev olarak eklenebilir.
- [x] compose healthcheck'leri (n8n, video-worker, media-gateway — cloudflared'ın minimal imajında
      pratik bir healthcheck komutu yok, atlandı) — `docker compose ps` artık gerçek sağlık durumu gösteriyor.
- [x] Kaçan cron telafisi (`app/catchup.py`) — açılışta bugün henüz çalışmamış ve zamanlanan saati
      (09:00/12:00 Europe/Istanbul) geçmiş bir iş varsa otomatik tetiklenir. video-worker'a
      `TZ=Europe/Istanbul` eklendi (önceden UTC'ydi, n8n'in cron saatiyle uyuşmuyordu).
      ⏳ Telegram'a günlük özet (ayrı bir digest mesajı) HENÜZ YOK — istenirse ayrı görev olarak eklenebilir.
- [x] `scripts/backup.py` — n8n-data + used_topics/used_image_topics/published_log'u tek komutla
      `backups/otomasyon-yedek-<tarih>.tar.gz`'a yedekler. **Otomatik değil** — Windows Task
      Scheduler'a eklenmesi kullanıcı eylemi (bkz. aşağıda).
- [ ] `/generate` → onay → `/publish` tam döngü entegrasyon testi (dış API'ler mock) — HENÜZ YOK.

### Faz 3 — İzlenecek içerik üret (3.–4. hafta) → K7, K10, K12 — kısmen tamamlandı (2026-09-05)

- [x] **K10 çözüldü (kökten):** `extract_keywords`'ü Türkçe script'ten çıkarım yapmaya zorlamak
      yerine, LLM'den script ile *birlikte* `visual_keywords` istendi — script Türkçe olsa bile
      bu alan HER ZAMAN İngilizce (stok kütüphane yalnızca İngilizce etiketli). Model bu isteğe
      bağlı alanı atlarsa `extract_keywords`'e düşülür — o yol için de Türkçe stopword listesi
      eklendi (savunma amaçlı, asıl çözüm değil).
- [x] **K7 kısmen:** Pexels'te `per_page=15` içinden rastgele seçim; kullanılan klip ID'leri
      `used_clips.json`'da hatırlanıp tekrar seçilmiyor (havuz tükenirse kısıtlama esner).
      ⏳ **Henüz yapılmadı:** LLM'den sahne planı (cümle başına ayrı visual query + TTS süresine
      bağlı sahne süresi) ve Ken Burns yakınlaştırma + crossfade geçişler — bunlar render.py'nin
      ffmpeg filtre grafiğini önemli ölçüde genişleten, ayrı bir oturumu hak eden bir iş.
- [ ] İlk 2 saniyeye hook, sonda CTA, marka bumper'ı
- [ ] Arka plan müziği + konuşma sırasında ducking; karaoke altyazı vurgusu
- [ ] Kapak görseli üretimi; başlık/açıklamayı platform başına ayrı üret

### Faz 4 — Öğrensin ve çoğalsın (5.–8. hafta) → K8, K9, K11

- [ ] SQLite iş kuyruğu: günde birden fazla içerik, paralel bekleyen işler
- [ ] X ve LinkedIn metriklerini haftalık rapora ekle
- [ ] Performans → konu seçimi geri bildirim döngüsü
- [ ] Dinamik konu üretimi: sabit 50'lik havuzun yerine LLM + gündem
- [ ] Çok markalı yapı: müşteri başına kimlik, konu havuzu, marka kiti, zamanlama
- [ ] Basit web paneli: bekleyen onaylar, geçmiş, metrikler

---

## Faz özeti

| Faz | Kapattığı bulgular | Süre | Durum |
|---|---|---|---|
| Faz 0 | K1 · K2 · K4 · K13 | ~3 saat | ✅ Tamamlandı (2026-09-05) |
| Faz 1 | K3 | 1 hafta* | ⏳ Kullanıcı eylemi bekliyor |
| Faz 2 | K5 · K6 · K13 | ~2 gün | 🟢 Neredeyse tamam (2026-09-05) — sadece entegrasyon testi kaldı |
| Faz 3 | K7 · K10 · K12 | ~2 hafta | 🟡 Kısmen tamamlandı (2026-09-05) — K10 çözüldü, K7 yarım, K12 beklemede |
| Faz 4 | K8 · K9 · K11 | ~4 hafta | Beklemede |

\* TikTok audit ve YouTube verification onayları dışarıdan gelir; süre senin elinde değil.

---

## Sıradaki adımlar

**Kullanıcı eylemi gerektirenler (kod düzeltemez):**

1. **Telegram bot token'ını yenile (K14).** BotFather → `/mybots` → botunu seç →
   API Token → Revoke current token. Yeni token'ı `.env`'e yaz,
   `docker compose up -d --build video-worker` çalıştır. Bu olmadan onay
   butonları güvenilmez çalışır (409 conflict).
2. **TikTok audit başvurusu (K3)** — henüz yapılmadıysa bugün başlat, en uzun süren adım.
3. **YouTube OAuth + verification (K3)** — aynı gün başvur, test modunda token 7 günde ölüyor.
4. **Meta, X, LinkedIn kimlikleri (K3)** — `docs/credential-kurulum.md`'deki adımlar.
5. **`scripts/backup.py`'yi Windows Task Scheduler'a haftalık ekle** (örn. Pazar 03:00) —
   script'in kendisi hazır, otomatik tetiklenmiyor.

**Kalan kod işleri (Faz 2 artıkları + Faz 3):** Telegram günlük özet,
`/generate`→onay→`/publish` entegrasyon testi, sahne planı + Ken Burns/crossfade
(K7'nin geri kalanı — ayrı bir oturumu hak eden en büyük parça), prodüksiyon
katmanı (K12: hook/müzik/kapak/karaoke altyazı).
