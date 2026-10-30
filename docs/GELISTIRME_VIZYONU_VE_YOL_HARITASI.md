# Genel Vizyon Analizi, Geliştirme Stratejisi ve Yol Haritası

- **Belge türü:** Vizyon analizi + önceliklendirilmiş yol haritası
- **Tarih:** 2026-10-29
- **Kapsam:** Mimari, içerik kalitesi, güvenlik, yayınlama, analitik, Documentary V2
- **Kaynak:** Kod tabanı denetimi (270 dosya / 48.128 satır) + resmî platform dokümantasyonu + açık kaynak proje araştırması
- **Durum:** Faz 0 P0 kısmen uygulandı (BGM regresyonu, hermetic test paketi, otonom yayın kilidi). Ayrıntı için bkz. "Uygulama durumu" eki.

---

## İçindekiler

1. [Genel vizyon değerlendirmesi](#1-genel-vizyon-değerlendirmesi)
2. [İnternet araştırmasının sonuçları](#2-internet-araştırmasının-sonuçları)
3. [En önemli ürün ve teknik boşluklar](#3-en-önemli-ürün-ve-teknik-boşluklar)
4. [Önerilen hedef mimari](#4-önerilen-hedef-mimari)
5. [Aşamalı geliştirme planı (Faz 0–6)](#5-aşamalı-geliştirme-planı)
6. [Önceliklendirilmiş iş listesi](#6-önceliklendirilmiş-iş-listesi)
7. [Yapılmaması gerekenler](#7-yapılmaması-gerekenler)
8. [Ölçülebilir başarı göstergeleri](#8-ölçülebilir-başarı-göstergeleri)
9. [İlk 30 günlük uygulanabilir yol haritası](#9-ilk-30-günlük-uygulanabilir-yol-haritası)
10. [Nihai öneri](#10-nihai-öneri)
11. [Kaynaklar](#11-kaynaklar)

---

## 1. Genel vizyon değerlendirmesi

Projenin mevcut hâli, "LLM'den metin alıp stok görüntü üzerine ses ve altyazı ekleyen" basit otomasyonlardan daha ileri bir yapıya sahip:

- FastAPI + FFmpeg tabanlı üretim (`video-worker/`)
- n8n ile zamanlanan işler
- Telegram ile insan onayı (long-polling, public adres gerektirmiyor)
- YouTube, TikTok, Instagram ve Facebook yayınlama adaptörleri
- X ve LinkedIn görsel kart akışı
- Haftalık analiz raporu
- Documentary V2: VLM destekli görsel doğrulama, EDL ve yeniden üretim denemeleri
- Günlük yakalama (`app/catchup.py`), retry ve iş durumu takibi

Bu nedenle doğru hedef **daha fazla özellik eklemek değil**, bunları tek bir üretim işletim sistemine dönüştürmek:

> **Araştırılan, kaynakları doğrulanan, görsel ve işitsel kalite kontrolünden geçen, insan onaylı ve yayın performansından öğrenen çok kanallı içerik stüdyosu.**

### Üç ana ürün ilkesi

1. **Önce içerik değeri, sonra otomasyon:** Her video izleyiciye yeni bir bilgi, bakış açısı veya hikâye sunmalı.
2. **Otomatik üretim, kontrollü yayınlama:** Üretim otomatik; doğruluk, marka ve yayın kararı ölçülebilir kurallarla ve gerektiğinde insanla kontrol edilmeli.
3. **Yayın sonrası öğrenme:** Sistem yalnızca video üretmemeli; hangi konu, hook, format ve sesin neden çalıştığını öğrenmeli.

### Mevcut durumun özet değerlendirmesi

| Boyut | Durum | Not |
|---|---|---|
| Üretim motoru | ✅ Olgun | FFmpeg yolu üretimde çalışıyor, Remotion deneysel |
| Zamanlama | ✅ Çalışıyor | n8n cron + catchup |
| İnsan onayı | ⚠️ Kısmen | Çalışıyor ama hash'e bağlı değil, çift mesaj riski var |
| Yayınlama | ⚠️ Kısmen | Adaptörler var; durum takibi ve idempotency zayıf |
| İçerik araştırması | ❌ Yok | Kaynak/claim doğrulama katmanı bulunmuyor |
| Kalite ölçümü | ⚠️ Kısmen | VLM doğrulama var ama yalnızca V2 yolunda (kapalı) |
| Analitik öğrenme | ❌ Yok | Rapor var, geri besleme döngüsü yok |
| Kalıcı veri modeli | ⚠️ Zayıf | JSON dosyaları tek gerçek kaynak |
| Test/CI | ❌ Zayıf | Network'e bağımlı testler, CI yok |
| Güvenlik | 🔴 Risk | Secret geçmişi, onaysız yayın yolu |

---

## 2. İnternet araştırmasının sonuçları

### 2.1 Resmî platform kuralları

| Kaynak | Projeye etkisi |
|---|---|
| **YouTube kanal para kazanma politikaları**<br>https://support.google.com/youtube/answer/1311392 | YouTube, Temmuz 2025'te "tekrarlayan içerik" politikasını **"inauthentic content"** olarak adlandırdı ve tanımına *tekrarlayan veya seri üretilmiş* içeriği açıkça dahil etti. Benzer şablonla seri üretilen, az değişiklik içeren veya başka kaynaklardan anlamlı katkı olmadan derlenen içerikler para kazanmaya uygun olmayabilir. Reused content politikası (yorum, klip, derleme, reaction) değişmedi. |
| **YouTube yapay zekâ açıklama kuralları**<br>https://support.google.com/youtube/answer/14328491 | Açıklama gerektiren durumlar: gerçek kişiyi söylemediği/yapmadığı bir şeyi yaparken göstermek, gerçek olay veya yerin görüntüsünü değiştirmek, gerçekte yaşanmamış gerçekçi sahne üretmek, videonun ana odağı olan AI müziği. Gerektirmeyen: gerçekçi olmayan AI içerik ve küçük/estetik düzenlemeler. **Açıklama tek başına para kazanmayı veya erişimi engellemez.** Sürekli açıklamayan üreticiler manuel etiket veya YPP'den çıkarma riskiyle karşılaşabilir. YouTube ayrıca C2PA metadata içeren içeriği otomatik etiketleyebilir. |
| **TikTok Content Posting API**<br>https://developers.tiktok.com/doc/content-posting-api-get-started | Public direct post için uygulama onayı ve `video.publish` scope gerekli. **Denetlenmemiş (unaudited) istemcilerle yayınlanan tüm içerik özel görünürlükle sınırlı.** Yayın öncesi `creator_info/query` zorunlu; `privacy_level_options`, `max_video_post_duration_sec` gibi kısıtlar buradan okunmalı. Video `FILE_UPLOAD` veya doğrulanmış domain'den `PULL_FROM_URL` ile yüklenebilir; işlem asenkron olduğundan `publish_id` ile `status/fetch` polling şart. Fotoğraf yayını ayrı uç kullanıyor (`/v2/post/publish/content/init/`). |
| **X API rate limits**<br>https://docs.x.com/x-api/fundamentals/rate-limits | Limitler uç bazında, uygulama/kullanıcı token tipine ve abonelik seviyesine göre değişiyor. `x-rate-limit-limit`, `x-rate-limit-remaining`, `x-rate-limit-reset` başlıkları ve `429` yanıtları okunmalı. Sabit retry yerine merkezi, uç bazlı bir limit/bütçe yönetimi gerekli. |
| **Meta Instagram API** | Profesyonel hesap gereksinimi ve container → publish → status akışı korunmalı. Medya URL'si public erişilebilir olmalı; ancak yönetim uçları (`/publish`, `/generate`, `/cleanup`) dışa açılmamalı. **Mevcut Caddy/media-gateway sınırı doğru bir tasarım kararı.** |

**Sonuç:** `daily_autonomous_agent.py` gibi Telegram onayını atlayıp doğrudan public yayın yapan yollar, yalnızca bir güvenlik problemi değil; yanlış bilgi, telif, platform politikası ve marka riski de taşıyor. Varsayılan olarak kapatılmalı veya taslak/özel yayın moduna alınmalı.

### 2.2 Açık kaynak ve üretim araçları

| Proje | Lisans | Alınabilecek yaklaşım | Yapılmaması gereken |
|---|---|---|---|
| **[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)** | MIT | Çok sağlayıcılı LLM/TTS desteği, `subtitle_provider` ile `edge`/`whisper` arasında geçiş, konu → anahtar kelime → stok klip akışı, WebUI + API ikilisi, "revision-aware local projects" (yalnızca etkilenen aşamaları yeniden derleme) fikri. | Projeyi bununla değiştirmek gereksiz. Repo'daki hazır müzikleri lisans doğrulaması yapmadan kullanmamak gerekir (README kendisi telif uyarısı yapıyor). |
| **[ShortGPT](https://github.com/RayVentura/ShortGPT)** | MIT | JSON tabanlı "Editing Markup Language" yaklaşımı, `ContentShortEngine` / `ContentVideoEngine` / `ContentTranslationEngine` ayrımı, çeviri + dublaj motoru fikri. | Deneysel ve görece eski motoru (MoviePy ağırlıklı) doğrudan üretim bağımlılığı yapmak. |
| **[WhisperX](https://github.com/m-bain/whisperX)** | BSD-2-Clause | wav2vec2 alignment ile kelime düzeyinde zamanlama, VAD tabanlı segmentleme, large-v2 ile ~70x realtime batched inference, opsiyonel diarization. Altyazı doğruluğunu **ölçmek** için ideal. | Diarization'ı kesin doğru kabul etmek; her video için ağır model çalıştırmak. Sayı/sembol içeren kelimeler (`"2014."`, `"£13.60"`) hizalanamıyor — bilinen sınırlama. |
| **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** | MIT | CTranslate2 ile daha ekonomik lokal transcription; CPU'da `int8` compute type ile çalışabilir. | CPU'da büyük modeli varsayılan yapmak. |
| **[OpenCut](https://github.com/OpenCut-app/OpenCut)** | MIT | Gelecekteki operatör/editör ihtiyacı için izlenebilir. Yol haritasında Editor API, plugin mimarisi, MCP server ve **headless mode (otomasyon/batch render)** var — bunlar tam olarak bu projenin ihtiyacı. | Şu an tabandan yeniden yazılıyor (`opencut-classic` eski sürüm). Dış katkı kabul etmiyor. Şimdi üretim motoruna bağlamak yanlış olur. |
| **[Remotion](https://www.remotion.dev/docs/license/faq)** | Source-available (**OSI açık kaynak değil**) | Programatik animasyon, React tabanlı tasarım sistemi, şablon bazlı markalı içerik. | "Açık kaynak" varsaymak. Bireyler ve ≤3 kişilik ekipler Free License kapsamında; daha büyük organizasyonlar Company License gerektiriyor. Lisans H.264/AAC gibi codec patent ücretlerini **kapsamıyor**. Repo'daki mevcut konumlandırma (`experimental / host-only`, `docker-compose` dışında) bu yüzden doğru. |
| **[C2PA / CAI açık kaynak SDK](https://opensource.contentauthenticity.org/docs/getting-started/)** | Açık kaynak | Manifest/assertion/claim/signature modeli; embedded, sidecar veya remote manifest saklama seçenekleri; ingredient ile kaynak asset'in provenance'ını zincirleme; CAWG kimlik assertion'ları. | C2PA'yı telif, gerçeklik veya AI açıklamasının yerine geçen bir garanti olarak sunmak. Manifest varlığı ≠ güven kanıtı (resmî doküman bunu açıkça belirtiyor). |

### 2.3 Araştırmanın ana çıkarımı

**Önerim:** Mevcut FFmpeg üretim yolunu koruyup kalite katmanlarını geliştirmek. Remotion'ı şimdilik yalnızca belirli şablonlar için opsiyonel tutmak; OpenCut'ı entegre etmek yerine gelecekteki editör ihtiyacı için izlemek. WhisperX/faster-whisper'ı **opsiyonel kalite doğrulama yolu** olarak eklemek, varsayılan render yolunu değiştirmemek.

Açık kaynak projelerin hiçbiri bu projenin asıl farklılaştırıcısını (onaylı + izlenebilir + çok platformlu yayın hattı) tek başına sağlamıyor. Yani rekabet avantajı **render teknolojisinde değil, üretim disiplininde**.

---

## 3. En önemli ürün ve teknik boşluklar

### A. İçerik üretimi hâlâ büyük ölçüde tek yönlü

Şu an ağırlıklı akış:

```text
konu → script → stok medya → TTS → altyazı → video → yayın
```

Olması gereken:

```text
trend ve kitle sinyali → kaynak araştırması → içerik açısı → kanıtlı script
→ storyboard → medya → kalite kontrol → onay → yayın → analiz → yeni içerik kararı
```

Kaynak araştırması ve performans geri beslemesi olmadan daha iyi render, tek başına izlenme veya kanal büyümesi sağlamaz. YouTube'un "inauthentic content" tanımı bu boşluğu doğrudan riske çeviriyor.

### B. Üretim yolları fazla ve sorumluluk sınırları net değil

- Legacy stock (`LEGACY_STOCK`)
- Director (`LEGACY_DIRECTOR`)
- Documentary V2 (`DOCUMENTARY_V2` / `DOCUMENTARY_V2_CANARY`)
- Remotion deneyi
- Görsel kart üretimi (X + LinkedIn)
- Ayrı otonom yayın ajanı (`daily_autonomous_agent.py`)

`app/main.py` üzerinde toplanan sorumluluk ve `app/documentary_v2/pipeline_mode.py` içindeki `V2_EXECUTION_ACTIVE = False` nedeniyle gerçekte çalışmayan V2, yatırımın görünür ürün değerine dönüşmesini engelliyor. `DOCUMENTARY_ENGINE_V2=true` yapılsa bile kod `LEGACY_*` moduna düşüyor — yani konfigürasyon ile gerçek davranış arasında sessiz bir fark var.

Bu yüzden yeni modüller yazmadan önce **tek bir iş modeli ve pipeline sözleşmesi** gerekli.

### C. "Kalite" tanımı henüz yeterince ölçülebilir değil

VLM'in "görsel uygun" demesi tek başına yeterli değil. Dört ayrı kalite boyutu olmalı:

1. **Doğruluk:** İddialar kaynakla destekleniyor mu?
2. **Görsel editoryal kalite:** Sahneler anlatıyı gerçekten taşıyor mu?
3. **Teknik kalite:** Ses, altyazı, kare, codec, süre ve dosya uygun mu?
4. **İzleyici kalitesi:** Hook, tempo, tamamlama ve geri dönüş nasıl?

Şu anda yalnızca 2 ve kısmen 3 ölçülüyor; 1 ve 4 hiç ölçülmüyor.

### D. Kalıcı veri modeli sınırlı

Konu ve bazı iş durumlarının JSON dosyalarında tutulması küçük kurulum için pratik; ancak çok kanallı yayın, asset provenance, deneyler ve idempotent job yönetimi için yetersiz kalıyor. Ayrıca denetimde tespit edilen **kilitsiz topic-state güncellemeleri** bu tasarımın doğrudan sonucu.

### E. Operasyonel temel hazır değil

Önceki denetim bulgularıyla doğrudan ilişkili olarak:

- Testlerde gerçek ağ/LLM çağrıları (`refine_script` mock'lanmadığı için 4 dosya askıda kalıyor)
- CI ve lint eksikliği
- Secret geçmişi riski (Git history'de TikTok Chromium profili ve backup arşivi)
- Onaysız yayın yolu (`daily_autonomous_agent.py`)
- İptal edilemeyen executor timeout'ları
- Eşzamanlılık ve çift onay mesajı problemleri
- Bağımlılık tanımı eksiklikleri (Playwright import ediliyor ama `requirements.txt`'de yok)
- 194 commit edilmemiş değişiklik
- `PHASE3_MUSIC_ENABLED=false` durumunda sessiz video üreten BGM regresyonu
- ~33 gün sonra konu tekrarı

Çözülmeden yeni sağlayıcılar eklemek toplam güvenilirliği düşürür.

---

## 4. Önerilen hedef mimari

### 4.1 Tek merkez: `ContentJob` ve aşamalı üretim sözleşmesi

Video, dokümanter ve görsel kart ayrı uygulamalar gibi değil, aynı iş modelinin farklı "recipe"leri olmalı.

```text
ContentJob
 ├─ brief / channel / language / audience
 ├─ research and source claims
 ├─ script and structured scene plan
 ├─ assets and rights/provenance
 ├─ narration and caption timings
 ├─ render recipe and artifact hashes
 ├─ quality results and estimated cost
 ├─ approval decisions
 ├─ platform publications
 └─ performance metrics and experiment labels
```

Her aşama aynı kurallara uymalı:

- Girdi ve çıktı şeması tanımlı
- Aynı girdiden tekrar üretilebilir veya cache'ten döndürülebilir
- Timeout, retry ve maliyet bütçesi tanımlı
- Hata durumunda iş kaybolmuyor
- Üretilen artefakt hash'leniyor
- Canlı sağlayıcı yerine test double kullanılabiliyor
- Prompt, model ve konfigürasyon sürümü kaydediliyor

Mevcut kodda bu kuralların bir kısmı zaten var (`RECOVERY_MAX_*`, `MAX_EXTRA_*`, `RECOVERY_MAX_GENERATION_COST_PER_VIDEO` gibi bütçeler). Eksik olan bunların **tüm yollarda ortak** uygulanması ve kalıcı olarak kaydedilmesi.

### 4.2 Modül sınırları

```text
api/             HTTP ve health
application/     job orchestration ve state machine
research/        kaynak, claim ve fact-check
scripting/       script, hook, scene plan
media/           stock/generated media ve rights
narration/       TTS ve transcript alignment
render/          FFmpeg EDL ve opsiyonel Remotion
quality/         teknik, görsel, editoryal kontroller
publishing/      platform adapter, approval ve idempotency
analytics/       metrik toplama ve deneyler
storage/         iş, artefakt ve metadata kalıcılığı
```

İlk geçişte tüm kodu taşımak yerine bu sınırlar `main.py` ve pipeline etrafında **adaptörlerle** oluşturulmalı. **Big-bang rewrite yapılmamalı.**

### 4.3 Durum makinesi

```text
DRAFT → RESEARCHED → SCRIPTED → PLANNED → RENDERED
      → QUALITY_REVIEW → AWAITING_APPROVAL
      → APPROVED → PUBLISHING → PUBLISHED
```

Kurallar:

- Başarısız aşama yeniden denenebilir olmalı
- Onay belirli bir `job_id + artifact_hash` için geçerli olmalı
- Onaydan sonra script veya video değişirse onay geçersizleşmeli
- Aynı platforma aynı içeriğin tekrar yayınlanması idempotency key ile engellenmeli
- Public yayın, yalnızca onay ve politika kontrolleri tamamlandıktan sonra yapılmalı
- `PUBLISHING` durumunda timeout olursa **yeniden yayın değil, önce durum sorgusu** yapılmalı

---

## 5. Aşamalı geliştirme planı

### Faz 0 — Güvenlik ve güvenilirlik temeli
**Öncelik: P0 / yaklaşık 1–2 hafta**

1. TikTok/Oturum/OAuth ve geçmişe sızmış olabilecek tüm credential'ları rotate et. Gerekirse `git filter-repo` ile history temizliği (rotation **zorunlu**, history rewrite opsiyonel).
2. Public otonom yayını varsayılan kapat; onaydan bağımsız çalıştırılmasını engelle.
3. `refine_script`, HTTP, TTS ve platform çağrılarını testlerde mock'la (4 askıdaki dosyayı çözer).
4. Network testlerini `live` marker ile ayır; per-test timeout ekle.
5. Legacy BGM kapalıyken oluşan sessiz video regresyonunu düzelt (sentetik ambient fallback).
6. Kalan bayat testleri güncelle (`/health`, Fal 403, gerçek DNS'e çıkan Documentary V2 testi).
7. Bağımlılıkları tek manifest/lock mekanizmasında netleştir; Playwright kararını ver (declare et veya host-only olarak belgele).
8. CI'a minimum kontrolleri ekle:
   - Ruff
   - pytest
   - Docker build
   - Secret scan
   - Dependency audit
9. Mevcut 194 değişikliği küçük, anlamlı commitlere böl ve temiz bir release baseline oluştur.

**Çıkış kriteri:** Network olmadan test paketi tamamlanmalı; her PR'da aynı kontroller çalışmalı; onaysız public yayın mümkün olmamalı.

---

### Faz 1 — Üretim omurgasını sadeleştirme
**Öncelik: P0–P1 / 2–4 hafta**

1. `ContentJob`, `Artifact`, `Approval`, `Publication` modellerini tanımla.
2. Başlangıçta küçük bir **SQLite** kalıcılık katmanı kullan; JSON'u tek gerçek kaynak olmaktan çıkar.
   - Tek kullanıcılı mevcut kurulum için PostgreSQL şart değil.
   - Çok worker veya çok kullanıcı ihtiyacında PostgreSQL'e geç.
3. Legacy ve Director'ı ortak aşama arayüzlerine bağla.
4. Onayları artefakt hash'i ile ilişkilendir; çift Telegram onay mesajını gider.
5. Platform yayınlarını ortak state machine ve idempotency katmanına al.
6. Topic-state güncellemelerini kilit/transaction altına al.
7. Alt süreçleri gerçekten sonlandırılabilen job runner tasarla (executor timeout iptali şu an etkisiz).
8. Kapsamlı dokümantasyon yerine kısa mimari karar kayıtları (ADR) ve çalıştırılabilir runbook ekle.

**Çıkış kriteri:** Aynı iş tekrar oynatıldığında çift yayın olmamalı; her yayın hangi script, medya, model ve onayla yapıldığı izlenebilmeli.

---

### Faz 2 — İçerik kalitesi ve araştırma katmanı
**Öncelik: P1 / 3–6 hafta**

1. Kanal bazlı `ContentBrief` oluştur:
   - Hedef kitle
   - İçerik sütunları
   - Ton ve yasaklı ifadeler
   - Video süresi
   - Dil
   - Marka ve görsel kurallar
2. `topics.json` yerine puanlanmış konu havuzu:
   - Güncellik
   - Kitle uyumu
   - Önceki performans
   - Kaynak bulunabilirliği
   - Tekrar riski (mevcut ~33 günlük tekrar penceresi buraya bağlanmalı)
   - Üretim maliyeti
3. Script için **claim–source** modeli:
   - Her önemli olgusal iddiaya kaynak
   - Kaynak URL ve erişim tarihi
   - Desteklenmeyen iddiaları yayın öncesi engelleme
   - Finans/sağlık gibi alanlarda daha sıkı kontrol
4. Birden fazla hook üretip küçük insan/değerlendirme setiyle seçmek.
5. Script'i sahnelerden önce değerlendirmek:
   - İlk saniyelerde konu net mi?
   - Tekrar var mı?
   - Somut örnek var mı?
   - Her sahne yeni bilgi ekliyor mu?
   - CTA izleyici vaadiyle uyumlu mu?
6. Deterministik kontrolleri LLM'den ayırmak:
   - Süre, yasaklı ifade, tekrar, kaynak varlığı → **kodla**
   - Anlatı ve ikna kalitesi → **LLM rubric** ile
   - Son yayın kararı → **insanla**

**Çıkış kriteri:** Yayınlanan her video için içerik brief'i, claim–source kaydı ve onaylı script sürümü bulunmalı.

---

### Faz 3 — Video ve ses kalitesi
**Öncelik: P1 / 3–5 hafta**

1. Mevcut edge-tts zamanlamalarını hızlı yol olarak koru.
2. Whisper/faster-whisper veya WhisperX'i **opsiyonel kalite yolu** olarak ekle:
   - Sayı, para birimi, özel isim hataları
   - Kelime hizalama eksikleri
   - Altyazının sesten sapması
   - *Not:* WhisperX sayı/sembol içeren kelimeleri hizalayamıyor — bu bilinen sınırlama için ayrı bir kural yazılmalı.
3. **Altyazı kalite kuralları**
   - Platform güvenli alanlarına uyum
   - Satır başına karakter ve maksimum satır sayısı
   - Minimum/maksimum görünme süresi
   - Okuma hızı ve sahne değişimleriyle senkron
   - Noktalama ve sayı biçimi
   - Kelime vurgusunda aşırı animasyondan kaçınma
4. **Ses kalite kontrolünü otomatikleştirme**
   - Sessiz veya eksik sesi yayın öncesi engelleme (BGM regresyonunun kalıcı çözümü)
   - Anlatı ve müzik seviyesini ayrı ölçme
   - FFmpeg `loudnorm` ile tutarlı seviye
   - Konuşma sırasında kontrollü ducking
   - Clipping, uzun sessizlik, ani seviye sıçraması tespiti
   - Son dosyanın süresinin anlatı ve sahnelerle uyuştuğunu doğrulama

   Hedefler kanal bazlı yapılandırılmalı; her platform için tek bir "sihirli LUFS değeri" varsayılmamalı.

5. **Görsel seçim kalitesi**
   - Sadece konu benzerliği değil, sahnenin işlevi de dikkate alınmalı:
     - Hook
     - Kanıt/açıklama
     - Örnek
     - Karşılaştırma
     - Sonuç
   - Aynı stok görüntünün videolar arasında tekrarını sınırlama
   - Görselin yönü, çözünürlüğü, hareketi ve kırpma sonrası kompozisyonunu değerlendirme
   - Yüz, metin veya önemli nesnenin yanlış kırpılmasını tespit etme
   - Görsel doğrulama sonucuna güven skoru ve gerekçe ekleme (mevcut `DIRECTOR_RELEVANCE_MIN` bu fikrin başlangıcı)
   - Düşük güvenli görseli otomatik değiştirme; tekrarlı başarısızlıkta insana gönderme
6. **Medya hakları ve kayıt sistemi**

   Her asset için:
   - Kaynak ve sağlayıcı
   - Kaynak URL'si
   - Lisans/kullanım bilgisi
   - İndirme tarihi
   - Orijinal dosya hash'i
   - AI ile üretilip üretilmediği
   - Kullanıldığı işler
   - Gerekirse AI açıklaması

   "Stok siteden geldi" bilgisi tek başına kalıcı lisans kaydı değildir. Pexels/Pixabay anahtarları var ama Mixkit için resmî API yok (HTML fallback) — bu kaynağın lisans durumu ayrıca doğrulanmalı.
7. **Render kalite kapısı**
   - FFprobe ile codec, süre, FPS, çözünürlük ve ses kanalı kontrolü
   - Bozuk kare ve decode hatası taraması
   - Başlangıç/orta/son karelerden otomatik temas sayfası
   - Kara ekran, donmuş görüntü, eksik altyazı tespiti
   - Küçük boyutlu önizleme ve tam render için ayrı onay
   - Son yayın dosyası ile onaylanan dosyanın hash eşleşmesi

**Çıkış kriteri:** Sessiz, bozuk, yanlış süreli, altyazısız veya lisans kaydı olmayan videolar yayın kuyruğuna girememeli. Her işte teknik kalite raporu üretilmeli.

---

### Faz 4 — Yayınlama güvenilirliği ve analitik öğrenme
**Öncelik: P1 / 3–4 hafta**

#### Yayınlama

Her platform için ortak adapter sözleşmesi:

```text
validate_account()
validate_media()
create_publication()
get_publication_status()
get_metrics()
refresh_credentials()
handle_rate_limit()
```

Ortak davranışlar:

- Yükleme başarısının yayın başarısı sayılmaması
- Uzun işleme durumlarının polling ile izlenmesi (TikTok `publish_id` → `status/fetch`)
- Platform sonucunun kalıcı olarak saklanması
- Timeout sonrasında körlemesine yeniden yayın yerine **önce durum sorgulama**
- Rate limit ve geçici hatalar için jitter/backoff (X'te `x-rate-limit-*` başlıkları)
- Kalıcı 4xx hatalarında otomatik tekrar yapılmaması
- Token süresi ve kapsamının sağlık kontrolünde izlenmesi
- Test hesabı / dry-run / private yayın modları
- Günlük yayın ve maliyet limitleri
- TikTok'ta `creator_info/query` ile `max_video_post_duration_sec` ve `privacy_level_options` kontrolü

#### Analitik

Haftalık metin raporundan, karar üreten bir sisteme geçilmeli:

- Video ve platform bazında yayın kimliği
- Gösterim, izlenme, izlenme süresi
- Ortalama izlenme ve tamamlama oranı
- Etkileşim, paylaşım, kaydetme
- Takipçi dönüşümü
- Yayın saati
- Konu, hook, format, süre, ses ve görsel şablon etiketleri
- Üretim maliyeti ve harcanan insan süresi

Metriklerin anlamı platformlar arasında farklı olabilir. Bu nedenle **ham metrik saklanmalı**, ortak normalize metrikler ayrıca tanımlanmalı.

#### Kontrollü deneyler

Başlangıçta karmaşık otomatik A/B altyapısı yerine:

1. Her videoda yalnızca **bir** ana değişkeni etiketlemek
2. Yeterli örneklem oluşmadan kesin sonuç üretmemek
3. Aynı videonun farklı platform sonuçlarını doğrudan kıyaslamamak
4. "En çok izlenen" yerine kanal hedefine uygun metriği seçmek
5. Sonuçları konu seçimine geri beslemek
6. Düşük performanslı videoları otomatik silmek veya yeniden yayınlamak yerine incelemek

**Çıkış kriteri:** Her yayın üretim işine bağlanmalı; haftalık rapor yalnızca sayıları değil, "gelecek hafta neyi değiştireceğiz?" sorusunu yanıtlamalı.

---

### Faz 5 — Documentary V2 kararı
**Öncelik: P1–P2 / 2–4 hafta**

V2'nin **24.386 satırlık** uygulama/test yatırımına rağmen `V2_EXECUTION_ACTIVE = False` olması ve Stage G canary dokümanında **5/5 başarısız iş** kaydı bulunması, önce ürün kararı verilmesi gerektiğini gösteriyor.

#### Önerilen karar: Tamamen silmek yerine daraltılmış canary

1. Tek bir kanal, tek bir içerik tipi ve kısa video formatı seçilmeli.
2. V2'nin gerçekten değer katan parçaları korunmalı:
   - Yapılandırılmış scene plan
   - VisualVerifier
   - EDL
   - Kalite sonrası kontrollü repair
   - Maliyet bütçeleri
3. İlk canary'de dışarıda bırakılabilecekler:
   - Otomatik public yayın
   - Sınırsız repair
   - Pahalı AI video üretimi (`STAGE_E_LIVE_GENERATION`, `GENERATED_VIDEO_PROVIDER=fal_kling`)
   - Çok sayıda alternatif renderer
   - Olgunlaşmamış tam otonom kararlar
4. Aynı brief ile Legacy ve V2 çıktıları karşılaştırılmalı:
   - İnsan kalite puanı
   - Teknik hata sayısı
   - Manuel müdahale süresi
   - Render süresi
   - Video başı maliyet
   - Yayın performansı
5. Belirlenen eşiği geçemezse V2 arşivlenmeli; yararlı modülleri ortak pipeline'a taşınmalı.

**Canary önerisi:** Önce 5–10 iş, private/dry-run yayın ve zorunlu insan onayı. Sonuçlar olumluysa trafik kademeli artırılmalı. Başarısız işlerde otomatik olarak Legacy'ye **sessizce** dönmek yerine neden ve mod açıkça kaydedilmeli (`resolve_pipeline_mode` zaten mod döndürüyor — bu kayda bağlanmalı).

**Çıkış kriteri:** V2'nin üretimde kalması, yalnızca testlerinin geçmesine değil, ölçülebilir kalite/maliyet avantajına bağlı olmalı.

---

### Faz 6 — Operatör deneyimi ve isteğe bağlı editör
**Öncelik: P2 / ihtiyaç oluştuğunda**

Telegram iyi bir onay mekanizması; fakat içerik yönetimi için sınırlı. İlk web arayüzü tam bir video editörü olmamalı.

#### Minimum operatör paneli

- İş listesi ve durumları
- Hata nedeni ve yeniden deneme
- Video önizleme
- Script ve kaynaklar
- Sahne bazlı medya görünümü
- Teknik kalite raporu
- Maliyet ve sağlayıcı kullanımı
- Onay/red ve değişiklik notu
- Platform yayın durumu
- Performans metrikleri

#### Sonraki aşamada

- Script cümlesini düzenleme
- Sahneye başka stok/AI medya atama
- Altyazı metni ve zamanını düzeltme
- Yeniden render yerine yalnızca değişen aşamayı çalıştırma (MoneyPrinterTurbo'nun "revision-aware projects" yaklaşımı)
- Sürüm karşılaştırma

Her değişiklik yeni artefakt sürümü oluşturmalı ve önceki onayı geçersiz kılmalı.

**OpenCut kararı:** Şimdilik entegre edilmemeli. Yeniden yazım süreci tamamlandığında headless render ve Editor API yeniden değerlendirilebilir.

---

## 6. Önceliklendirilmiş iş listesi

| Öncelik | İş | Değer | Bağımlılık |
|---|---|---|---|
| P0 | Credential rotation ve onaysız yayını kapatma | Güvenlik ve marka koruması | Yok |
| P0 | Hermetic testler, CI, BGM regresyonu | Güvenilir geliştirme | Yok |
| P0 | Temiz commit/release baseline | Değişikliklerin izlenebilirliği | Yok |
| P1 | Ortak job state machine ve idempotent yayın | Çift yayın ve veri kaybını önler | Temel testler |
| P1 | Hash bağlı onay ve yayın kalite kapısı | Yanlış içeriğin yayınını önler | Job modeli |
| P1 | Kalıcı iş/asset/publication metadata | İzlenebilirlik ve analiz | Job modeli |
| P1 | Kaynaklı araştırma ve claim doğrulama | İçerik güvenilirliği | Brief modeli |
| P1 | Ses, altyazı ve teknik render kontrolleri | İzlenir çıktı kalitesi | Artifact modeli |
| P1 | Yayın sonrası metrikleri üretim işine bağlama | Öğrenen sistem | Publication modeli |
| P1 | V2 canary veya arşiv kararı | Teknik yatırımın değere dönüşmesi | Ortak pipeline |
| P2 | Konu seçiminde performans geri beslemesi | Kanal büyümesi | Yeterli analitik veri |
| P2 | Operatör paneli | Daha hızlı müdahale | Stabil API/state |
| P2 | Lokal Whisper kalite yolu | Altyazı doğruluğu | Donanım benchmark |
| P2 | C2PA provenance pilotu | Şeffaflık ve içerik kökeni | Asset provenance |
| P3 | Gelişmiş editör, çok kullanıcı, çok kiracı mimari | Ölçeklenebilir ürün | Gerçek kullanıcı ihtiyacı |

---

## 7. Yapılmaması gerekenler

1. **Mevcut sistemi baştan yazmamak:** Çalışan yayın/onay/render yatırımı korunmalı.
2. **Documentary V2'yi doğrudan tüm trafiğe açmamak:** Stage G sonuçları (5/5 başarısız) bunu desteklemiyor.
3. **Her yeni AI modelini sisteme eklememek:** Model değişimi, ölçülmüş kalite veya maliyet avantajı gerektirmeli.
4. **LLM'i tek doğruluk hakemi yapmamak:** Deterministik kontroller, kaynak doğrulaması ve insan onayı ayrı kalmalı.
5. **Şimdilik Kubernetes/Kafka veya mikroservislere geçmemek:** Mevcut ölçek için operasyonel yük gereksiz.
6. **Otomatik altyazı için her videoda büyük Whisper modeli çalıştırmamak:** Önce hata oranı ve donanım maliyeti ölçülmeli.
7. **Tam otomatik public yayını büyüme hedefi yapmamak:** Hedef, daha az insan müdahalesi değil; daha güvenli ve daha iyi içerik olmalı.
8. **C2PA'yı zorunlu ilk iş yapmamak:** Önce asset provenance ve AI açıklama kararları uygulanmalı.
9. **Tüm platformlara aynı videoyu değişiklik yapmadan göndermeyi büyüme stratejisi saymamak:** Başlık, açıklama, kapak, süre ve güvenli alanlar platforma uyarlanmalı.
10. **Remotion'ı "açık kaynak" varsayarak ticari otomasyonda genişletmemek:** Lisans ve codec patent koşulları ayrıca değerlendirilmeli.
11. **Denetlenmemiş TikTok istemcisiyle public yayın beklememek:** Unaudited istemcilerde içerik private kalır; büyüme planı buna göre kurulmalı.

---

## 8. Ölçülebilir başarı göstergeleri

Başlangıç hedefleri, mevcut baseline ölçüldükten sonra kesinleştirilmeli.

### Güvenilirlik

| Gösterge | Hedef |
|---|---|
| CI'da network'süz test başarısı | `%100` |
| Onaysız public yayın | `0` |
| Aynı işin çift yayınlanması | `0` |
| Yayın sonucu bilinmeyen işler için otomatik durum sorgusu | `%100` |
| Yayın dosyası ile onaylı dosya hash eşleşmesi | `%100` |

### İçerik ve teknik kalite

| Gösterge | Hedef |
|---|---|
| Sessiz/bozuk video yayını | `0` |
| Önemli olgusal iddialarda kaynak kaydı | `%100` |
| Asset kaynak/lisans metadata kapsamı | `%100` |
| Manuel kalite reddi ve ret nedenleri | Zaman içinde azalmalı |
| Script veya medya yüzünden tekrar render oranı | Azalmalı |

### Operasyon

- Video başı toplam üretim maliyeti
- Video başı render süresi
- İnsan müdahale süresi
- Başarılı işler için ortalama deneme sayısı
- Hataların aşama ve sağlayıcıya göre dağılımı

### Büyüme

- Kanal ve format bazında tutma/tamamlama
- Paylaşma ve kaydetme
- Takipçi dönüşümü
- İçerik sütunu bazında tekrar izleyici davranışı
- Üretim maliyetine göre içerik performansı

> **Önemli:** Ham görüntülenme tek North Star metriği olmamalı. Kanal amacına göre "nitelikli izlenme + takipçi dönüşümü + sürdürülebilir üretim maliyeti" birlikte değerlendirilmelidir.

---

## 9. İlk 30 günlük uygulanabilir yol haritası

| Dönem | Odak | Somut teslimat |
|---|---|---|
| **1. hafta** | Güvenlik ve test | Secret rotation, otonom yayın kilidi, hermetic testler, BGM düzeltmesi, CI |
| **2. hafta** | Pipeline sözleşmesi | `ContentJob`, durum makinesi, artefakt manifest, hash bağlı onay tasarımı |
| **3. hafta** | Yayın güvenilirliği | Idempotency, publication status polling, merkezi retry/rate-limit, SQLite kalıcılığı |
| **4. hafta** | Kalite ve ölçüm | Teknik kalite kapısı, asset provenance, yayın–analitik ilişkisi, V2 karar dokümanı |

30. günün sonunda sistem daha fazla özellik içermek yerine şu sorulara güvenilir biçimde cevap verebilmeli:

1. Hangi içerik üretildi ve neden?
2. Hangi kaynaklar ve medya kullanıldı?
3. Hangi model, prompt ve konfigürasyon çalıştı?
4. Kalite kontrollerinden geçti mi?
5. Kim, hangi sürümü onayladı?
6. Hangi platformda gerçekten yayınlandı?
7. Ne kadar maliyet ve insan müdahalesi gerekti?
8. Yayın performansı bir sonraki içerik kararını nasıl etkileyecek?

---

## 10. Nihai öneri

Ana strateji **"daha otonom video fabrikası" değil, "güvenilir ve öğrenen içerik stüdyosu"** olmalı.

Öncelik sırası:

1. **Güvenliği ve testleri düzelt.**
2. **Tek iş modeli ve yayın durum makinesi kur.**
3. **Kalite, kaynak ve medya provenance kapıları ekle.**
4. **Yayın analitiğini üretim kararlarına bağla.**
5. **V2'yi küçük canary ile kanıtla veya arşivle.**
6. **Ancak bundan sonra editör ve ölçekleme özelliklerine geç.**

Bu yaklaşım, mevcut FastAPI/FFmpeg/n8n/Telegram yatırımını korurken; sistemi hem platform politikalarına daha dayanıklı hem de gerçek içerik kalitesi ve kanal büyümesi üretebilen bir yapıya dönüştürür.

---

## 11. Kaynaklar

### Resmî platform dokümantasyonu

- YouTube kanal para kazanma politikaları (inauthentic/reused content): https://support.google.com/youtube/answer/1311392
- YouTube yapay zekâ içeriği açıklama kuralları: https://support.google.com/youtube/answer/14328491
- TikTok Content Posting API — Direct Post: https://developers.tiktok.com/doc/content-posting-api-get-started
- X API v2 rate limits: https://docs.x.com/x-api/fundamentals/rate-limits
- Meta Instagram API — Content Publishing: https://developers.facebook.com/docs/instagram-api/content-publishing/

### Açık kaynak projeler

- MoneyPrinterTurbo (MIT): https://github.com/harry0703/MoneyPrinterTurbo
- ShortGPT (MIT): https://github.com/RayVentura/ShortGPT
- WhisperX (BSD-2-Clause): https://github.com/m-bain/whisperX
- faster-whisper (MIT): https://github.com/SYSTRAN/faster-whisper
- OpenCut (MIT): https://github.com/OpenCut-app/OpenCut
- C2PA / Content Authenticity Initiative açık kaynak SDK: https://opensource.contentauthenticity.org/docs/getting-started/

### Ticari/source-available

- Remotion lisans SSS (source-available, OSI açık kaynak **değil**): https://www.remotion.dev/docs/license/faq

### Proje içi referanslar

- `README.md` — render stack, n8n kurulumu, credential durumu, security note
- `docs/superpowers/specs/2026-09-03-sosyal-medya-video-otomasyon-design.md` — mimari
- `docs/superpowers/plans/2026-09-03-sosyal-medya-video-otomasyon.md` — uygulama planı
- `docs/superpowers/plans/2026-09-05-mukemmellik-plani.md`
- `docs/superpowers/plans/2026-09-24-storytelling-correction.md`
- `docs/superpowers/plans/2026-09-25-documentary-v2-topic-review.md`
- `docs/superpowers/plans/2026-09-29-documentary-v2-stage-g-canary.md`
- `docs/superpowers/plans/2026-09-29-stage-g-story-pipeline-targeted-repair.md`
- `video-worker/app/config.py` — bütçe/limit ve Phase 3 bayrakları
- `video-worker/app/documentary_v2/pipeline_mode.py` — `V2_EXECUTION_ACTIVE`, mod çözümü

---

## 12. Uygulama durumu (2026-10-30)

Faz 0'ın P0 çekirdeği uygulandı ve doğrulandı.

### Yapılanlar

| # | Değişiklik | Dosya | Etki |
|---|---|---|---|
| 1 | Sentetik ambient fallback strict daldan çıkarılıp iki dalın paylaştığı tek bloğa taşındı | `video-worker/app/audio_bgm.py` | `PHASE3_MUSIC_ENABLED=false` + boş BGM dizini artık **sessiz video üretmiyor** |
| 2 | Sessiz video uyarısı `phase3_music` koşulundan çıkarıldı | `video-worker/app/pipeline.py:440` | Sessizlik her modda loglanıyor |
| 3 | Onaysız public yayın explicit opt-in'e bağlandı (`ALLOW_AUTONOMOUS_PUBLISH`) | `scripts/daily_autonomous_agent.py` | `--director` olmadan ve 180 sn timeout sonrası **otomatik public yayın kapanmış** |
| 4 | Ambient `.env` sızıntısı (`DIRECTOR_ENABLED`, `DOCUMENTARY_ENGINE_V2`) paylaşılan conftest'te temizlendi | `video-worker/tests/conftest.py` (yeni) | Testler mock'ladıkları legacy yolu gerçekten çalıştırıyor; canlı Pexels/LLM + 429 retry (~30 sn/test) bitti |
| 5 | `app.pipeline.refine_script` stub'landı | `video-worker/tests/conftest.py` | Wikipedia + LLM editör çağrıları ve askı bitti |
| 6 | `live` / `live_smoke` markları kaydedildi | `video-worker/pytest.ini` | Canlı testler ayrıştırılabilir, uyarılar temizlendi |
| 7 | Bayat testler düzeltildi | `tests/test_main.py`, `tests/test_ai_visuals.py`, `tests/test_documentary_v2_stage_d1.py`, `tests/test_phase_a_quality.py` | `/health` kesin-eşitlik, gerçek Fal 403, gerçek DNS (`example.invalid`), eksik `voice_settings` kwarg'ı |
| 8 | İkinci `/publish` artık reddediliyor | `video-worker/app/jobs.py`, `app/main.py`, `app/errors.py`, `app/telegram_bot.py` | Çift tıklama / n8n retry / Telegram double-callback aynı videoyu **iki kez public yayınlayamıyor** (409) |
| 9 | Onay butonları `job_id`'ye bağlandı | `video-worker/app/telegram_bot.py`, `app/pipeline.py` | Eski bir mesajdaki "Onayla"ya basmak **yanlış videoyu yayınlayamıyor** |
| 10 | Onay video dosyasının **hash'ine** bağlandı | `app/pipeline.py`, `app/main.py`, `app/publish_log.py`, `app/errors.py` | Aynı `job_id` altında yeniden render edilen farklı içerik eski onayla **yayınlanamıyor** (409) |
| 11 | Yükleme zaman aşımı "başarısız" değil **"bilinmiyor"** | `app/main.py`, `app/errors.py`, `app/telegram_bot.py` | Zaman aşımında retry butonu sunulmuyor → **zaten yayınlanmış video ikinci kez yüklenemiyor** |

### Ölçülen sonuç

| Metrik | Önce | Sonra |
|---|---|---|
| Tam paket | **tamamlanamıyordu** (4 dosya askıda) | **623 passed, 3 skipped, 0 failed** |
| Süre | belirsiz (askı) | **115 sn** |
| Başarısız test | 5 | **0** |

### Belirsiz sonuç ayrımı (madde 11)

`_run_parallel_uploads` **her** exception'ı — `fut.result(timeout=300)` zaman aşımı dahil — `status="error"` olarak kaydediyordu. Ama thread bekleme bırakıldıktan sonra da çalışmaya devam eder, yani video platformda **yayınlanmış olabilir**. Tümü "error" görününce `main` dosyayı `failed/`'a taşıyıp retry sidecar yazıyordu; Telegram'daki "🔁 Tekrar dene" butonu **zaten yayınlanmış videoyu** yeniden yüklüyordu. `claim_for_publish` bunu kapatamaz, çünkü `failed` durumunu meşru retry için bilinçli olarak claim edilebilir bırakıyoruz.

- Zaman aşımı artık `status="unknown"` (gerçek exception `"error"` kalıyor)
- Herhangi bir `unknown` sonucu, all-failed dalına girmeden önce kısa devre yapıyor: **retry sidecar yazılmıyor**, medya dosyası taşınmıyor/silinmiyor
- `PublishOutcomeUnknownError` → HTTP **502**; Telegram yolu retry butonu olmadan "platformu kontrol edin, tekrar denemeyin" diyor

### Artefakt hash doğrulaması (madde 10)

`job_id` **saniye çözünürlüklü** (`main.py:54/259/299`), yani yeni bir render aynı `media_dir/{job_id}.mp4` yoluna yazabilir. Onay yalnızca job id'ye bağlı olduğu sürece, onaylanan dosya farklı içerikle değiştirilip yine yayınlanabilirdi.

- `pipeline.py` onay payload'ına `video_sha256` yazıyor (varsa split-screen, yoksa cinematic dosya)
- `/publish` özeti **claim'den önce** yeniden doğrular → uyuşmazlık veya kayıp dosya `ArtifactChangedError` → **409**, hiç yükleme yapılmaz
- Doğrulama claim'den önce çalışır, aksi halde reddedilen bir yayın işi `publishing`'de kilitli bırakırdı
- Özet yoksa **fail-open** → legacy/curl çağrıları ve görsel akışı çalışmaya devam eder

Test sırasında iki hata yakalandı: **(1)** `PublishRequest` `video_sha256` alanını tanımlamıyordu, Pydantic onu sessizce düşürüyordu → koruma ölü kod olurdu; **(2)** `_verify_approved_artifact` yalnızca `video_path`/`split_screen_path`'e bakıyordu, görsel işlerinin `image_path`'ini kaçırıyordu.

### Onay hedefleme detayı (madde 9)

`handle_callback` eskiden `data == "approve"` kontrolüyle **o an pending olan her ne ise** onu yayınlıyordu. Butonlar statikti (`"approve"`), yani A işinin mesajındaki butona basıldığında B işi yayınlanabiliyordu. Scratch bir üreme ile kanıtlandı: eski yol tıklanan buton "A"ya aitken **"B"yi yayınladı**; yeni yol hiçbir şey yayınlamıyor.

- Butonlar artık `approve:<job_id>` / `reject:<job_id>` taşıyor (`_approval_keyboard()`)
- `handle_callback` hedefi `_target_payload()` ile çözer; güncel pending işle eşleşmezse reddeder
- Eski `job_id`'siz butonlar **fail-closed**: tahmin etmek yerine açıklayıcı mesajla reddedilir
- `_target_payload` çözülen payload ile karşılaştırır, çünkü `read_pending_payload` `job_id`'yi SQLite satırından geri dolduruyor → yukarı akış çağıranlarının hiçbiri değişmedi
- Dört buton üretim yeri güncellendi: `pipeline.py` onay bildirimi, pitch önizlemesi, doğal mesaj render'ı, paylaşılan helper

### Yayın idempotency detayı (madde 8)

`claim_for_publish()` tek bir `UPDATE jobs SET state='publishing' WHERE id=? AND state NOT IN ('publishing','done')` çalıştırır ve `rowcount` üzerinden yarışı kazanıp kazanmadığını söyler. Bu, "oku-sonra-yaz" yarışını kapatır: iki eşzamanlı `/publish` çağrısından yalnızca biri yükleme yapar, diğeri `409` alır. Korunan davranışlar:

- `failed` durumu **claim edilebilir kalır** → Telegram "Tekrar dene" butonu çalışmaya devam eder
- Job satırı **hiç yoksa** yayın geçer → image/legacy akışları job oluşturmaz, bunları reddetmek yayıncıyı kırardı
- Telegram botu `AlreadyPublishedError`'ı yakalayıp kullanıcıya "atlandı" mesajı gösterir; bu hata `AllPlatformsFailedError` değildir, retry payload yazmaz

### Kök neden notu

Askı sanılan şey aslında **gerçek ağ retry'ı**ydı: `.env` içindeki `DIRECTOR_ENABLED=true` yüzünden legacy stock yolu mock'lanan testler Director yolunu gerçekten çalıştırıyordu (`api.pexels.com` 429 backoff + LLM 401). Bir testte `scene_plan` → `director_clips_ready` arası 31 sn sürüyordu. Aynı bayrak birçok test dosyasında elle `delenv` ediliyordu; conftest bunu bir kez yapıyor.

### Henüz yapılmadı

- Credential rotation ve Git history temizliği
- Lint (bilinçli olarak atlandı: kod tabanında lint baseline yok, varsayılan ruff/flake8 ilk koşuda kırmızı olur ve CI'ı görmezden gelmeye alıştırır)
- Playwright kararı → **verildi**: CI'a eklenmedi, host-only kaldı (hiçbir test `tiktok_browser`'ı import etmiyor)
- `pytest-timeout` ile per-test timeout (yeni bağımlılık gerektiriyor)
- Push (8 commit lokal `cursor/hybrid-flux-architecture` dalında)
- `video-worker/video-output/*` üretilmiş artefaktları ve `_tmp_*` scratch dizinleri (bilinçli olarak commit edilmedi)
- Faz 1'in geri kalanı (ContentJob artefakt manifesti, publication durum sorgulama, kalite kapıları)

### Commit geçmişi

| Commit | İçerik |
|---|---|
| `4291c74` | Sessiz video regresyonu, hermetic test paketi, otonom yayın kilidi (9 dosya) |
| `6fbee82` | İzlenmeyen video-worker kaynak ağacı — HEAD artık import edilebilir (107 dosya, bana ait değil) |
| `7e3d1cd` | CI workflow (`.github/workflows/ci.yml`) |
| `69effc9` | Bu belgeye uygulama durumu |
| `7200d5f` | Yayın idempotency: `claim_for_publish` + 409 (6 dosya) |
| `bdf50e4` | Onay butonları `job_id`'ye bağlandı (3 dosya) |
| `ad944cb` | Onay video hash'ine bağlandı (7 dosya) |
| `a615fa6` | Zaman aşımı "bilinmiyor" olarak ayrıldı (4 dosya) |

> Bu belgeyi güncelleyen commit ayrıca `docs:` önekiyle geçmişte bulunabilir (kendi hash'ini içeremez).

> `6fbee82` zorunluydu: commit edilen `app/pipeline.py`, `app/documentary_v2/__init__.py` ve `pipeline_mode.py`'yi import ediyordu ama bunlar hiç commit edilmemişti. Taze klon import aşamasında patlıyordu, yani CI eklenemezdi.
