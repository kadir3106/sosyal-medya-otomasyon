# Sosyal Medya Video Otomasyon Sistemi — Tasarım

**Tarih:** 2026-09-03
**Durum:** Onaylandı (kullanıcı tarafından, brainstorming oturumunda)

## 1. Amaç

Her gün otomatik olarak bir "faceless" (yüzsüz/anlatıcısız) kısa video üretip, insan onayı (Telegram üzerinden) aldıktan sonra YouTube Shorts, TikTok, Instagram Reels ve Facebook Reels'e aynı anda yükleyen; haftalık performans raporu çıkaran, tamamen ücretsiz araçlarla çalışan bir otomasyon sistemi kurmak.

## 2. Kapsam ve Kısıtlar

- **Dil:** İngilizce
- **Niş:** Genel bilgi/eğlence (ilginç bilgiler, kısa hikayeler, "did you know" tarzı içerik) — AI script üretimi bu nişe göre prompt'lanır
- **Format:** Faceless slideshow — AI script + TTS seslendirme + stok video/görsel klipler + gömülü altyazı, FFmpeg ile birleştirilir. Text-to-video AI modelleri (Runway/Pika vb.) KULLANILMAZ — ücretsiz kotalar yetersiz ve kalite tutarsız.
- **Sıklık:** Günde 1 video, dikey 9:16 formatında, aynı dosya 4 platforma da yüklenir (platform başına ayrı render YOK)
- **Bütçe:** Sıfıra yakın — sadece ücretsiz API katmanları ve self-hosted araçlar kullanılır
- **Onay:** Tek aşamalı — sadece final video Telegram'a onaya sunulur (script/topic ayrıca onaylanmaz)
- **Analiz:** Sadece performans takibi + haftalık Telegram raporu. Geçmiş performansın gelecek konu seçimini etkilediği bir AI geri bildirim döngüsü v1 kapsamı DIŞINDA (YAGNI — gelecekte eklenebilir).
- **Platformlar:** YouTube, TikTok, Instagram Reels, Facebook Reels. X/Twitter kapsam dışı.

## 3. Mimari

### 3.1 Bileşenler (Docker Compose, 2 servis + 1 shared volume)

```
docker-compose.yml
├── n8n            (n8nio/n8n resmi image, SQLite backend)
│     - Cron trigger (günlük video üretim akışı)
│     - Cron trigger (haftalık analiz akışı)
│     - Telegram Trigger/node (onay butonları, callback query dinleme)
│     - HTTP Request node'ları (video-worker'ı çağırma, platform upload API'leri)
├── video-worker   (özel Python/FastAPI image)
│     - POST /generate  → video üretir, dosya yolu + metadata döner
│     - GET /health
└── shared-media   (Docker named volume, iki container'a da mount edilir)
      - üretilen mp4/mp3/altyazı dosyaları burada yaşar
```

**Neden bu ayrım:** n8n karmaşık prosedürel mantığı (script bölme, FFmpeg komut zinciri, altyazı senkronu) okunabilir/test edilebilir şekilde ifade edemiyor — bu yüzden "gerçek iş" ayrı, test edilebilir bir Python servisine taşınıyor. n8n sadece zamanlama + insan onayı + platform entegrasyonu (asıl güçlü olduğu alan) için kullanılıyor.

### 3.2 video-worker iç akışı (`/generate` endpoint)

1. **Konu seçimi:** `topics.json` içindeki ~50 önceden hazırlanmış konu havuzundan, `used_topics.json` state dosyasına bakarak henüz kullanılmamış bir konu seçilir (round-robin). Havuz tükenirse baştan başlanır.
2. **Script üretimi:** OpenRouter API'ye (`qwen/qwen3-coder:free` veya benzeri ücretsiz model) konu + niş talimatıyla prompt gönderilir, ~150-200 kelimelik anlatım script'i + başlık + açıklama (YouTube/TikTok/Instagram için) JSON formatında istenir.
3. **Seslendirme:** `edge-tts` Python paketi ile script İngilizce bir sesle (örn. `en-US-GuyNeural`) MP3'e çevrilir, kelime zamanlamaları (word boundaries) da alınır (altyazı senkronu için).
4. **Stok görsel/video:** Script'ten anahtar kelimeler çıkarılır (basit noun-phrase extraction), Pexels API'den (ücretsiz, API key gerekli) script uzunluğuna yetecek sayıda dikey stok klip indirilir.
5. **Render:** FFmpeg ile klipler sırayla birleştirilir, TTS ses track'i eklenir, kelime zamanlamalarından üretilen altyazılar (SRT → burned-in subtitle) video üzerine gömülür, 9:16 1080x1920 çıktısı `shared-media` volume'üne yazılır.
6. **Yanıt:** `{video_path, title, description, tags}` JSON olarak n8n'e döner.

### 3.3 Günlük n8n workflow'u

```
Cron (09:00 günlük)
  → HTTP Request: POST video-worker:8000/generate
  → Telegram: sendVideo (video + caption: title/description) + inline keyboard [✅ Onayla | ❌ Reddet]
  → Telegram Trigger: callback_query bekle
      ├── "approve" ise:
      │     → HTTP Request: YouTube Data API v3 videos.insert (resumable upload)
      │     → HTTP Request: TikTok Content Posting API /publish/video/init + upload
      │     → HTTP Request: Meta Graph API /{ig-user-id}/media + /media_publish (Instagram)
      │     → HTTP Request: Meta Graph API /{page-id}/video_reels (Facebook)
      │     → Telegram: her platformun sonucunu özetleyen mesaj (başarı ✅ / hata ❌ + sebep)
      └── "reject" ise:
            → shared-media'dan dosyayı sil
            → Telegram: "İptal edildi, yarın yeni video" mesajı
```

Her platform upload adımı `continueOnFail` ile ayarlanır — biri başarısız olsa diğerleri denenmeye devam eder, hepsi Telegram özetinde raporlanır.

**TikTok istisnası:** TikTok Content Posting API'de app "audited" (denetlenmiş) durumda değilse, `privacy_level` zorunlu olarak `SELF_ONLY` olur — video sadece hesap sahibine görünür, herkese açık paylaşılamaz. Audit onaylanana kadar sistem TikTok'a otomatik yükler ama private modda; onay çıktıktan sonra `privacy_level` değeri koddan `PUBLIC_TO_EVERYONE` olarak güncellenir.

### 3.4 Haftalık analiz workflow'u

```
Cron (Pazartesi 10:00)
  → HTTP Request: YouTube Analytics API (son 7 gün: views/likes/comments per video)
  → HTTP Request: TikTok Video List/Query API (istatistikler)
  → HTTP Request: Meta Graph API insights (Instagram/Facebook)
  → Code node: sonuçları tek bir özet tabloya birleştir
  → Telegram: haftalık özet mesajı (platform, video, izlenme, beğeni, yorum)
```

Bu workflow yalnızca raporlama yapar; hiçbir otomatik karara (konu seçimi, script tonu vb.) etki etmez.

## 4. Kurulum ön koşulları (henüz elde olmayanlar)

| Gereksinim | Durum | Not |
|---|---|---|
| YouTube Data API v3 key/OAuth | ✅ Mevcut | |
| Telegram bot token | ✅ Mevcut (BotFather) | |
| Docker | ✅ Kurulu | Docker Desktop servisinin çalışır durumda olması gerekiyor |
| OpenRouter API key | ✅ Mevcut (CLAUDE.md'de kayıtlı) | |
| Pexels API key | ❌ Yok | Ücretsiz, anında alınabilir (pexels.com/api) |
| TikTok Developer app + audit başvurusu | ❌ Yok | Kayıt + app oluşturma anında; audit onayı günler/haftalar sürebilir → **en erken başlatılmalı** |
| Meta Developer app + Instagram Business hesabı bağlantısı | ❌ Yok | Kayıt anında; kendi hesabına Development modunda review olmadan yükleme yapılabilir |

## 5. Hata yönetimi

- Her platform upload adımı bağımsız try/catch; biri patlarsa diğerleri devam eder
- video-worker herhangi bir adımda (TTS/stok medya/render) hata verirse n8n'e `500` + hata mesajı döner, n8n bunu Telegram'a "bugün video üretilemedi: <sebep>" olarak iletir, o gün upload adımı hiç tetiklenmez
- Reddedilen/başarısız videoların dosyaları `shared-media`'dan temizlenir (disk şişmesin diye)

## 6. Test yaklaşımı

- **video-worker:** pytest ile her adım (konu seçimi, script parse, TTS çağrısı, FFmpeg komutu) ayrı ayrı test edilir; dış API çağrıları (OpenRouter, Pexels) mock'lanır; gerçek bir "test video" end-to-end üretimi manuel doğrulama adımı olarak yapılır.
- **n8n workflow'ları:** n8n'in "Execute Workflow" manuel tetikleme özelliğiyle her workflow ayrı ayrı, gerçek (ama test/private) Telegram chat'ine ve platformların sandbox/private modlarına karşı test edilir.
- **Platform upload'ları:** İlk testler her zaman private/unlisted modda yapılır (YouTube: unlisted, TikTok: self-only zaten zorunlu, Instagram/Facebook: kendi test hesabı) — gerçek public yayına geçiş son adım olarak elle onaylanır.

## 7. Kapsam dışı (v1, gelecekte değerlendirilebilir)

- Performans verisine dayalı otomatik konu/ton optimizasyonu (AI feedback loop)
- İki aşamalı onay (script + video ayrı ayrı)
- Platform başına farklı uzunluk/format render (örn. YouTube için uzun-form)
- X/Twitter desteği
