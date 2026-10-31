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
| 12 | Sahte zaman aşımı düzeltildi — tamamlanan yükleme artık okunuyor | `app/main.py` | Başarılı yayın "bilinmiyor" diye raporlanmıyor; operatör hayalet aramıyor |
| 13 | Fan-out bütçesi yayıncı timeout'larıyla hizalandı (300 → 660 sn) | `app/main.py` | 600 sn süren YouTube/TikTok/Meta yüklemeleri artık **ortasında kesilmiyor** |
| 14 | `append_publish_log` kilitlendi + atomik yazıyor | `app/publish_log.py` | Eşzamanlı yayın kayıtları kaybolmuyor (ölçüm: 40 kayıttan **35'i kayıptı**) |
| 15 | Konu seçimi kilitlendi; desen paylaşılan `jsonstore`'a çıkarıldı | `app/jsonstore.py` (yeni), `app/topics.py`, `app/publish_log.py` | Eşzamanlı seçim **aynı konuyu tekrar dağıtmıyor** (ölçüm: 40 çağrıda 3 farklı konu, **30 tekrar**) |
| 16 | `/generate` guard'ı + iş kaydı tek atomik adım; `job_id` benzersiz | `app/jobs.py`, `app/main.py`, `app/pipeline.py` | İki eşzamanlı istek **tek üretim** başlatıyor (ölçüm: `[200,200]`/2 çağrı → `[200,409]`/1 çağrı) |
| 17 | `/publish`'in bilinmeyen-iş dalı atomik yapıldı (koşullu INSERT) | `app/jobs.py`, `app/main.py`, `tests/test_publish_concurrency.py` (yeni) | Legacy/görsel iş **iki kez kamuya açık yayınlanamıyor** (ölçüm: 2 yayın/8 yükleme → 1 yayın/4 yükleme) |
| 18 | Eşzamanlı silmede geçici `WinError 5` yeniden deneniyor | `app/main.py`, `tests/test_publish_concurrency.py` | Paralel `/cleanup` **500 dönmüyor** (ölçüm: 8 thread'de 20/20 → 0/20) |
| 19 | Kapı testi `frozenset` sırasına bağımlı olmaktan çıkarıldı | `tests/test_director_gate_regression.py` | Test **hash seed'e göre dalgalanmıyor** (ölçüm: 6 farklı sıralama → 30 seed'de 0 hata) |
| 20 | Dış ağ engellendi, `session` retry politikası testlerde sıfırlandı | `tests/conftest.py` | **203 dış bağlantı → 0**; paket 72 sn → **50 sn**; `.env` yokken de 646 passed |
| 21 | Yayın kaydı `job_id` + `approved_sha256` taşıyor; manifest okuyucusu ve `provenance.trace_publication` eklendi | `app/publish_log.py`, `app/provenance.py` (yeni), `app/documentary_v2/telemetry.py`, `app/main.py`, `app/analytics.py` | "Bu yayın hangi işin/manifestin/onayın ürünü?" **artık cevaplanıyor** (`trace.complete=True`); manifest okuyan tüketici 0 → 1 |
| 22 | Yayın öncesi teknik kalite kapısı (süre/ses akışı/ortalama seviye) | `app/publish_quality.py` (yeni), `app/errors.py`, `app/main.py`, `app/telegram_bot.py` | Sessiz/boş/çok kısa video **yayınlanamıyor** (ölçüm: sessiz -91 dB → red, sesli -21 dB → geçti); reddedilen dosya claim'i tüketmiyor; Telegram'da retry butonu sunulmuyor |
| 23 | Timeout sonrası gerçek durum sorgusu: `inflight` kimlik kaydı + TikTok/YouTube API | `app/publish_status.py` (yeni), `app/publishers/publication_status.py` (yeni), `app/publishers/{tiktok,youtube}.py`, `app/main.py` | Sorgu "yayınlandı" derse iş **`done`** olur (`publish_recovered_after_timeout`) — körlemesine retry riski kalktı; token diske yazılmıyor |
| 24 | Kalıcı performans defteri + konu seçiminde performans sıralaması + hook hafızası beslemesi | `app/performance_ledger.py` (yeni), `app/analytics.py`, `app/topics.py`, `app/analytics_memory.py`, `app/{pipeline,main}.py` | Döngü kapandı: prompt eki **0 → 229 karakter**; konu seçimi havuz sırası yerine **ölçülmüş performansı** kullanıyor |

### Ölçülen sonuç

| Metrik | Önce | Sonra |
|---|---|---|
| Tam paket | **tamamlanamıyordu** (4 dosya askıda) | **726 passed, 3 skipped, 0 failed** |
| Süre | belirsiz (askı) | **50 sn** (dış ağ engeli + retry kapalı) |
| Başarısız test | 5 | **0** |

### Konu seçimi yarışı (madde 15)

`select_next_topic` kilit yok + oku-değiştir-yaz yapıyordu. Ölçüm:

```
calls: 33                              ← 40 çağrıdan 7'si çöktü (JSONDecodeError)
distinct topics handed out: 3           ← 40 çağrıda yalnızca 3 farklı konu
duplicates handed out: 30               ← aynı konu 30 kez tekrar dağıtıldı
```

Düzeltmeden sonra: **40/40 farklı konu, 0 tekrar, 0 çökme.**

Tekrar eden konu = tekrar eden içerik. Bu, doğrudan YouTube'un "inauthentic content" politikasının hedeflediği durum.

Aynı desen iki modülde görüldüğü için kopyalamak yerine paylaşılan `app/jsonstore.py`'a çıkarıldı (`locked_json` / `read_json` / `write_atomic`). `publish_log.py`'deki önceki kopya **silindi** — net satır sayısı arttı ama desen artık tek yerde.

- `write_atomic`: aynı dizine geçici dosya + `os.replace`; hata durumunda geçici dosya temizleniyor
- `read_json`: bozuk dosyayı `<ad>.corrupt` olarak kenara alıp temiz başlıyor
- Kilit **süreç-içi**; `video-worker` tek replika çalıştığı için yeterli

### Üretim guard'ı yarışı (madde 16)

`/generate` guard'ı (`pending.json` + `has_blocking_job`) ile `create_job` **iki ayrı adımdı** — arada `await generate_video` var, o da işi `asyncio.to_thread`'e devredip event loop'u serbest bırakıyor. Ölçüm:

```
/generate  codes=[200, 200] invocations=2 RACE=True     ← iki istek de geçti
```

`delay=0` ile de tekrarlanıyor; yani yavaş bir LLM çağrısına ihtiyaç yok, pencere **yapısal**. Ayrıca `job_id` saniye çözünürlüğündeydi:

```
ids: ['20261031-070512', '20261031-070512']   collision: True
distinct work dirs: 1                          ← iki pipeline aynı dizine yazıyor
rows in jobs table: 1 (expected 2)             ← bir iş tamamen kayıp
```

İki video üretiliyor, ara dosyalar birbirini eziyor, tek satır kalıyor.

Düzeltme: `job_store.claim_new_job()` guard'ı ve INSERT'i **tek koşullu `INSERT ... SELECT ... WHERE NOT EXISTS`** yapıyor; SQLite'ın yazma kilidi denetle-ve-yaz'ı atomik kılıyor. `/generate`, `/generate-image` ve `_run_generate_sync` (Telegram "tekrar dene" + açılış yakalama) önce talep ediyor, `job_id`'yi aşağı geçiriyor. `new_job_id()` 6 hex sonek ekliyor (`20261031-070512-a1b2c3`, 21 bayt — Telegram'ın 64 baytlık `callback_data` sınırına rahat sığar).

Düzeltmeden sonra: `/generate` → `[200, 409]`, tek çağrı; 10 eşzamanlı talep → tam 1 kazanan, 1 satır.

Yan bulgu: `has_blocking_job` `generating` için de True olduğundan, hâlâ üretim yapan bir iş için operatöre "Telegram'dan onayı çöz" deniyordu — var olmayan bir onaya yönlendirme. `_conflict_detail` artık `get_awaiting_approval`/`pending.json` üzerinden ayırıyor.

Not: `claim_new_job` içindeki `pending.json` kontrolü atomik INSERT'in dışında. Legacy/curl akışı DB satırı oluşturmadan yalnızca bu dosyayı yazdığı için kontrol kaldırılamaz — iki mevcut test bunu yakaladı. Dosya tarafı atomik değil, DB tarafı atomik.

### Yayın kaydı yarışı (madde 14)

`append_publish_log` tüm dosyayı kilit olmadan oku-değiştir-yaz yapıyordu ve `main._run_publish` paralel yayın sonuçlarını buradan yazıyor. Ölçüm:

```
appends attempted: 40
entries actually stored: 5
LOST: 35
JSONDecodeError: Expecting value: line 1 column 1   ← dosya bozuldu
```

Düzeltmeden sonra: **40/40 kaydedildi, 0 kayıp**.

- Süreç-içi kilit (`threading.Lock`) oku-değiştir-yaz'ı serileştiriyor
- **Atomik yazma**: aynı dizine geçici dosya + `os.replace` → okuyucu asla yarım dosya görmez
- Bozuk dosya artık yayın yolunu çökertmiyor: `<ad>.corrupt` olarak kenara alınıp log temiz başlıyor (kanıt korunuyor)

### Bütçe / yayıncı timeout uyumsuzluğu (madde 13)

Ölçüm: `youtube.py:64`, `tiktok.py:63` ve `meta.py:130` video gövdesini **`timeout=600`** ile yüklüyor; fan-out bütçesi ise `_PUBLISH_TIMEOUT_SECONDS = 300` idi.

```
largest publisher request timeout: 600
current budget: 660
OLD budget 300 would have been cut off: True
```

Yani 300 sn'yi aşan **her** video yüklemesi garanti olarak ortasında kesiliyor ve yanlış `"unknown"` raporlanıyordu — madde 11 ve 12'de kovaladığım hayaletin asıl kaynağı buydu.

- Bütçe **660 sn** (600 sn tek PUT + token/init/poll/publish için 60 sn pay)
- İki değerin tekrar ayrışmaması için **sözleşme testi** eklendi: `app/publishers/*.py` içindeki en büyük `timeout=` değerini tarar, bütçe onu geçmiyorsa test kırılır
- `tiktok_browser.py` hariç: host-only ve oradaki `timeout=` değerleri Playwright DOM beklemeleri (milisaniye), HTTP timeout değil

### Sahte zaman aşımı bulgusu (madde 12)

Madde 11'i uygularken ölçtüm ve **kendi düzeltmemin yanlış olduğunu** gördüm:

```
reported: TimeoutError                      ← "bilinmiyor" dedik
elapsed: 0.40                               ← aslında bekledik
side effects that really happened: ['PUBLISHED:x']
real outcome was: {'platform': 'x', 'status': 'success'}
```

`with ThreadPoolExecutor(...)` bloktan çıkarken `shutdown(wait=True)` çağırıyor, yani `fut.result(timeout=...)` süresi dolsa bile blok **worker bitene kadar bekliyordu**. Yükleme gerçekten tamamlanıyor, ama biz `"unknown"` yazıyorduk → başarılı yayın çözümsüz görünüyor, dosya silinmiyor, operatör olmayan bir sorunu araştırıyordu.

- Bağlam yöneticisi yerine açık `pool` + `finally: pool.shutdown(wait=False)`
- Tüm future'lar için **tek bir monotonic son tarih** (eskiden her future 300 sn alabiliyordu → 7 platformda toplam 2100 sn)
- Doğrulama: 3 sn'lik görev, 0.1 sn bütçeyle **0.11 sn**'de dönüyor ve henüz yan etki yok → `"unknown"` artık dürüst
- Ayrıca eksik `import time` eklendi (`NameError` verirdi)

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

**Madde 17 — "satır yoksa geç" dalı atomik değildi.** Yukarıdaki `UPDATE` yalnızca *var olan* satırı koruyordu; satır yoksa karar `SELECT` + `return known is None` ile veriliyordu — yani denetle-ve-yaz. `/publish` senkron `def` olduğu için FastAPI onu threadpool'da çalıştırır, iki istek **gerçekten paralel** koşar. Ölçüm (2 eşzamanlı `/publish`, DB satırı yok):

| | Önce | Sonra |
|---|---|---|
| Başarılı yayın | **2** | **1** |
| Platform yüklemesi | **8** (4×2) | **4** |
| İkinci istek | `ok` | `AlreadyPublishedError` → 409 |

Düzeltme: bilinmeyen iş, `UPDATE`'in zaten açtığı yazma kilidi içinde **koşullu bir INSERT** ile talep edilir; birincil anahtar hakemdir, kaybeden `IntegrityError` alır. `kind` yalnızca oluşturulan satırı etiketler.

Yan etki kapatıldı: satır artık *oluştuğu* için beklenmeyen bir çökme onu `publishing`'de bırakıp `/generate`'i **sonsuza dek 409**'a kilitleyebilirdi. `_run_publish`, kendi işlemediği her istisnada claim'i `failed`'a bırakır (`failed` claim edilebilir → retry hâlâ çalışır).

### Kök neden notu

Askı sanılan şey aslında **gerçek ağ retry'ı**ydı: `.env` içindeki `DIRECTOR_ENABLED=true` yüzünden legacy stock yolu mock'lanan testler Director yolunu gerçekten çalıştırıyordu (`api.pexels.com` 429 backoff + LLM 401). Bir testte `scene_plan` → `director_clips_ready` arası 31 sn sürüyordu. Aynı bayrak birçok test dosyasında elle `delenv` ediliyordu; conftest bunu bir kez yapıyor.

### Henüz yapılmadı

- Credential rotation ve Git history temizliği
- CI'ın kalan 2 kontrolü: `docker build` (Docker daemon bu ortamda çalışmıyor → yerelde doğrulanamadı, bu yüzden eklenmedi) ve `ruff` (lint baseline yok)
- Playwright kararı → **verildi**: CI'a eklenmedi, host-only kaldı (hiçbir test `tiktok_browser`'ı import etmiyor)
- `pytest-timeout` ile per-test timeout (yeni bağımlılık gerektiriyor)
- ~~Push (41 commit lokal `cursor/hybrid-flux-architecture` dalında)~~ → **yapıldı** (2026-10-31): dallar `origin/cursor/hybrid-flux-architecture` üzerinde, CI her push'ta koşuyor (madde 25 ve 26.1)
- `video-worker/video-output/*` üretilmiş artefaktları ve `_tmp_*` scratch dizinleri (bilinçli olarak commit edilmedi)
- Faz 1'in geri kalanı (ortak job state machine, ayarlanabilir artefakt manifesti versiyonlama)
- Teknik kalite kapısının kalan boyutları: altyazı zamanlaması/satır kuralları, clipping, ani seviye sıçraması, `loudnorm` hedefi doğrulaması (şu an süre + ses akışı + ortalama seviye kontrol ediliyor)
- Yayın sonucu bilinmeyen işler için durum sorgusu yalnızca **TikTok ve YouTube**'da var; X/LinkedIn/Pinterest/Instagram/Facebook yükleme anında kimlik üretmediği için desteklenmiyor
- YouTube'da `video_id` ancak yükleme yanıtıyla geliyor: read-timeout daha erken oluşursa kimlik yok (kodda belgelendi)
- Zombi upload thread'leri için süreç düzeyinde izolasyon (`shutdown(wait=False)` artık beklemiyor; thread'ler süreç bitene kadar yaşayabilir)
- `jsonstore` kilidi yalnızca **süreç-içi**; birden çok video-worker replikası çalışırsa dosya düzeyinde kilit gerekir
- `jobs.py` `write_pending_mirror` hâlâ düz `write_text` ile yazıyor (atomik değil); okuma tarafı artık SQLite'ı tercih ettiği için pratikte yarım dosya okunmuyor ama dosya düzeyinde garanti yok
- `claim_new_job` içindeki `pending.json` kontrolü atomik INSERT'in **dışında** — DB tarafı atomik, dosya tarafı değil (legacy akış yalnızca kendi yazarıyla yarışabilir)
- `claim_for_publish`'in "satır yok" dalı artık atomik, ama `_verify_approved_artifact` (hash doğrulaması) ile claim arasında dosya değişebilir: hash kontrolü kendi başına atomik değil, yalnızca TOCTOU penceresini daraltıyor
- `/cleanup` için yarış ölçüldü ve düzeltildi; ama `_run_cleanup`'ın `pending.json` üzerinden `mark_done` çağırması ile eşzamanlı bir `/publish` hâlâ teorik olarak yarışabilir (ikisi de farklı kilitler kullanıyor)

### Eşzamanlı silme (madde 18)

İki istek aynı artefaktı silmeye çalışınca Windows'ta kaybeden taraf `PermissionError` (`WinError 5`) alıyor — kazanan hâlâ dosya tutamacını bırakmamış oluyor. `unlink(missing_ok=True)` yalnızca `FileNotFoundError`'ı yutuyor, dolayısıyla paralel `/cleanup` çağrılarından biri **500** dönüyordu. Dosya kaybı yoktu (zaten siliniyordu), ama çağıran gerçek bir arıza görüyordu.

Ölçüm (8 thread, 20 deneme): `20/20` hata. Hata sonrası `path.exists()` kontrolü **yetmiyor** — aynı şekilde yarışıyor ve 10 denemede 1 kez hâlâ patlıyordu. Çözüm: 10 ms'den başlayıp ikiye katlanan, en fazla 5 denemelik kısa retry. Kazanan mikrosaniyeler içinde bitiyor, retry `FileNotFoundError` görüyor. Gerçekten kilitli dosya son denemede yine hata veriyor (test bunu da kapsıyor).

Aynı desen `_run_publish`'in başarı-sonrası temizliğinde de vardı; tek yardımcıya (`_unlink_quietly`) çıkarılıp ikisi de ona bağlandı.

### Dalgalı kapı testi (madde 19)

`test_bakery_cookie_metadata_must_reject_for_wilsdorf_scene`, `gate.forbidden_hit`'in elle yazılmış bir "foodish" whitelist'inde olduğunu doğruluyordu. `DEFAULT_FORBIDDEN_CONCEPTS` bir **frozenset**: hangi kavramın ilk eşleştiği `PYTHONHASHSEED`'e bağlı. Ölçüm: 6 farklı seed → 6 farklı ilk-5 sıralama. Whitelist setin tamamını kapsamıyordu (`cook`, `foods`, `burger`, `sushi`...), bu yüzden test ~12 koşuda 1 kez kırılıyordu.

Bu bir **test kırılganlığıydı, üretim hatası değil**: kapı her durumda reddediyordu (`accepted=False`, `reason="forbidden_concept"`). İddia artık gerçek sözleşmeye bakıyor — eşleşen kavram gerçekten yasaklı setin elemanı mı. 30 farklı seed'de 0 hata.

> Bu hata ilk kez tam pakette, `/publish` değişiklikleriyle aynı koşuda göründü. Değişiklikler `git stash`'lenip paket yeniden koşturularak benim neden olmadığım doğrulandı (644 passed), sonra izole koşuda 12 denemede 1 kez üreyerek kaynağı bulundu.

### Dış ağ sızıntısı (madde 20)

Paket "hermetic" değildi: `DIRECTOR_ENABLED`/`DOCUMENTARY_ENGINE_V2` temizlenmiş olsa da testler hâlâ gerçek ağa çıkıyordu. Ölçüm (her soket bağlantısını loglayan bir sarmalayıcıyla, 100 test): **203 dış bağlantı denemesi**. Kaynaklar `_ensure_synthetic_ambient`'in ffmpeg yardımcıları, Pollinations görsel fallback'i, Wikipedia doğrulaması ve stub'lanmayı unutmuş yayıncılardı — yerel `.env`'de 23 kimliğin 14'ü canlı olduğu için bunlar gerçek API çağrısına dönüşüyordu (`api.x.com` 400 bunun kanıtı).

Bunlar **bağımlılık değil, sızıntı**: aynı soketleri tamamen engelleyince paket yine `exit 0` verdi. Maliyetleri gerçekti — API kotası harcıyor, koşuları yavaşlatıyor ve ağ dalgalanmasına açık hale getiriyorlardı.

`conftest.py`'ye `_block_external_network` eklendi: loopback dışı her `connect`'i reddediyor. Loopback açık kalıyor çünkü Starlette `TestClient` anyio portalını yerel soket üzerinden kuruyor. Reddetme **düz `OSError`** ile yapılıyor, `requests` istisnasıyla değil: ilk sürüm `requests.ConnectionError` fırlatıyordu ve urllib3 bunu 3 kez 1,5 kat backoff ile yeniden denedi, paket 72 sn → **312 sn** oldu. Düz `OSError` yeniden denenmiyor.

Bu tek başına yetmedi (344 sn), çünkü `app.http_client.session` modül düzeyinde tekil ve `Retry(total=3, backoff_factor=1.5)` taşıyor. İkinci guard (`_disable_http_retries`) o politikayı her test için sıfırlıyor; `session.adapters` sözlüğü yedeklenip geri konuyor, böylece üretim politikasını doğrulayan `test_http_client` hâlâ `total == 3` görüyor. (İlk denemem mount'ları geri almadı ve o iki testi kırdı — modül düzeyinde tekil bir nesneye kalıcı mount, testler arası sızıntıdır.)

Sonuç: **646 passed, 3 skipped, 50 sn** (sızıntılı 72 sn, engelli ama retry'lı 344 sn).

> Aynı koşuda `test_publish_concurrency` da düzeltildi: paket çalışırken `jsonstore`'un gerçek `jobs.db`'sini kirletiyordu.

### Yayın → iş → manifest zinciri (madde 21)

Faz 1'in çıkış kriteri "her yayın hangi script, medya, model ve onayla yapıldığı izlenebilmeli". Ölçtüm, zincir kopuktu — ama göründüğü gibi değil:

| Ölçüm | Sonuç |
|---|---|
| Manifest her üretimde yazılıyor mu? | **Evet** (`DOCUMENTARY_ENGINE_V2_MANIFEST_<job_id>.json`, `pipeline.py`'de `emit_legacy_job_manifest`) |
| Yayın kaydı hangi anahtarları taşıyor? | `['kind', 'platforms', 'published_at', 'title']` |
| Kayıtta `job_id` var mı? | **Hayır** |
| Manifesti okuyan tüketici sayısı | **0** |

Yani 24k satırlık telemetri altyapısı her iş için dosya üretiyordu, ama **hiçbir kayda bağlanmıyor ve hiç kimse okumuyordu**. Üç sorun birbirini gizlemiş.

Düzeltme üç parça:

1. `publish_log.build_publish_entry()` — kaydın tek şeması. Artık `job_id` ve `approved_sha256` taşıyor. İkincisi bilinçli: onayın hangi dosyaya verildiğinin tek doğrulanabilir kanıtı.
2. `telemetry.manifest_path()` + `read_production_manifest()` — yazıcı ve okuyucu **aynı** adlandırmayı kullanıyor. Önce ayrı yazılsaydı zincir sessizce kopabilirdi; bir test bunu kilitliyor.
3. `app/provenance.py` (yeni) — `trace_publication()`: yayın kaydını işe ve manifeste bağlar, `sha256_match` ile onay-dosya uyumunu ve `complete` ile izin tam olup olmadığını döndürür. Eksik parça hata değil, `None` — eski kayıtlarda `job_id` yok ve bu normal.

Ayrıca `load_recent_entries` sağlamlaştırıldı: bozuk JSON'da artık çökmüyor ve `job_id`'siz eski kayıtları filtre dışı bırakmıyor (önce `e["published_at"]` doğrudan erişiliyordu).

Ölçüm sonrası: kayıt anahtarları `['approved_sha256', 'job_id', 'kind', 'platforms', 'published_at', 'title']`, `trace.complete = True`.

### Yayın öncesi kalite kapısı (madde 22)

Yol haritası hedefi "sessiz/bozuk video yayını = 0". Ölçtüm: `_run_publish` videoyu **hiç açmıyordu** — `app/main.py`'de yalnızca `_verify_approved_artifact` vardı, yani *"onayladığım dosya mı?"* sorusu soruluyordu, *"yayınlanabilir bir dosya mı?"* sorusu hiç sorulmuyordu. BGM regresyonu (sessiz video) üretim tarafında düzeltilmişti ama yayın öncesi ikinci savunma hattı yoktu. Onaylanmış süresi 0 veya sesi boş bir MP4 yayınlanabilirdi.

`app/publish_quality.py` (yeni) gerçek medyayla ölçüldü — ffmpeg ile üretilen dosyalar üzerinde:

| Durum | Karar | Ölçüm |
|---|---|---|
| Sesli video (440 Hz tone) | ✅ geçti | -21.1 dB |
| Sessiz video (boş ses akışı) | ❌ **reddedildi** | `audio_silent`, -91.0 dB |
| Ses akışı yok | ❌ reddedildi | `no_audio_stream` |
| 1 sn video | ❌ reddedildi | `too_short` |
| Bozuk konteyner | ✅ geçti | `probe_unavailable` |
| Dosya yok | ❌ reddedildi | `video_missing` |

Tasarım kararı: kapı **yumuşak**. Ölçüm alınamazsa (ffprobe yok, bozuk konteyner) yayın bloklanmıyor — video-worker ffprobe olmadan da çalışmaya devam etmeli. Yalnızca *ölçülmüş* ihlal engelliyor. Aynı sebeple `bgm_silence` tek başına ret nedeni değil: sentetik ambient fallback'i de sessiz görünebilir, gerçek ses ölçümü daha güvenilir.

Kritik sıra detayı: kapı `claim_for_publish`'ten **önce** çalışıyor. Aksi hâlde reddedilen video claim'i tüketir, iş `publishing`'de kalır ve `/generate` sonsuza dek 409 verirdi — bu hata daha önce bir kez yaşanmıştı (madde 17). Bir test bunu kilitliyor: reddedilen videoda `has_blocking_job` `False` kalmalı ve hiçbir platform çağrılmamalı.

HTTP karşılığı **422** (409 değil): dosya var ve onaylı, ama yayınlanabilir değil. Retry aynı dosyayla aynı sonucu verir; operatör yeniden üretmeli. Görsel kartlar kapıyı atlıyor — onlarda ses akışı beklenmiyor.

Telegram tarafı da bağlandı: `QualityGateError` yakalanmazsa operatör ham bir hata görürdü. Artık ret nedeni Türkçe okunur metne çevriliyor ("ses tamamen sessiz", "video çok kısa"…) ve **retry butonu sunulmuyor** — aynı dosyayı tekrar göndermek aynı sonucu verir, buton operatörü sonsuz döngüye sokardı.

### Timeout sonrası durum sorgusu (madde 23)

Yol haritası kuralı (Faz 4): *"Timeout sonrasında körlemesine yeniden yayın yerine **önce durum sorgulama**."* Ölçtüm: bu kural **uygulanamıyordu** — hiçbir yayıncıda durum sorgulayan fonksiyon yoktu. `status="unknown"` tek savunmaydı: retry butonu sunmuyorduk (doğru) ama işi kurtarmak için de hiçbir şey yapamıyorduk; operatör platformu elle kontrol etmek zorundaydı.

Kök neden bir **zamanlama** sorunuydu: platform kimliği (`tiktok` → `publish_id`, `youtube` → `video_id`) ancak `upload_to_*` döndüğünde elimize geçiyordu. Timeout tam yükleme sırasında oluştuğu için kimlik kayıptı. TikTok'ta `publish_id` **büyük gövde yüklenmeden önce** alınıyor — kritik detay bu.

Üç parçalı çözüm:

1. **`inflight` kaydı** (`app/publish_status.py`) — yayıncı kimliği üretilir üretilmez `media/inflight/<job_id>.json` dosyasına yazılıyor. Thread takılsa bile çağıran taraf sorgulayabilir.
2. **`PublishStatus`** — platformdan bağımsız normalize durum: `published` / `pending` / `failed` / `unknown`. `unknown` bilinçli olarak `published`dan ayrı, çünkü ikisi aynı operatör kararını gerektirmiyor.
3. **Gerçek API sorguları** (`app/publishers/publication_status.py`) — resmî dokümantasyondan doğrulandı:
   - TikTok `POST /v2/post/publish/status/fetch/` (`publish_id` gövdede) → `PUBLISH_COMPLETE` / `FAILED` + `fail_reason` / `PROCESSING_*`
   - YouTube `GET /youtube/v3/videos?part=status,processingDetails&id=...` → `uploadStatus` + `processingStatus`

`_run_publish`'in timeout dalı artık **gerçekten soruyor**: sorgu `published` derse iş `done` olur ve `publish_recovered_after_timeout` loglanır — bu bir **başarıdır**, hata değil. Retry sunmak operatörü aynı videoyu ikinci kez yayınlamaya iterdi. Sorgu doğrulayamazsa belirsizlik sürer ve retry yine sunulmaz.

Bilinçli sınırlar:
- **X, LinkedIn, Pinterest, Instagram, Facebook** desteklenmiyor: yükleme anında hiçbir kimlik bilinmiyor. Sorgu uydurmak yerine açıkça `unknown` diyoruz.
- **YouTube'da kimlik geç geliyor**: `video_id` yalnızca yükleme yanıtıyla gelir. Yükleme tamamlanıp yanıt gecikirse kayıt kurtarır; read-timeout daha erken oluşursa kimlik hiç yoktur. Bu sınır kodda belgelendi.
- **Erişim token'ı diske yazılmıyor**: `inflight` dosyası `media/` altında düz JSON; token oraya sızar ve secret scan'in kapsamı dışında kalırdı. Token sorgu anında canlı yenileniyor. Bunu bir test kilitliyor (`test_inflight_never_persists_access_token`) — ilk tasarımımda token yazılıyordu, kendi testim yakaladı.

### Analitik → üretim geri besleme döngüsü (madde 24)

Yol haritasının üçüncü ilkesi: *"Yayın sonrası öğrenme — sistem hangi konu, hook, format ve sesin neden çalıştığını öğrenmeli."* Ölçtüm: döngü **açıktı**, ama yarısı zaten yazılmıştı:

| Parça | Durum |
|---|---|
| `analytics_memory.format_hook_memory_context` pipeline'da okunuyor | ✅ (`pipeline.py:247`) |
| `store_winning_hook` **çağıran** | **0** |
| `analytics.py` içinde diske yazma | **YOK** — rapor her seferinde platformdan yeniden çekiliyor |
| `topics.py` içinde performans sinyali | **YOK** |
| Boş defterle prompt eki | **0 karakter** |
| Elle yazılırsa | **203 karakter** ← okuma tarafı sağlamdı |

Yani hafıza mekanizması vardı, onu besleyen hiçbir şey yoktu. Her rapor sayıları ekrana basıp atıyordu.

Düzeltme üç parça:

1. **`app/performance_ledger.py`** (yeni) — kalıcı metrik defteri. Ham metrik saklanıyor (yol haritası: *"ham metrik saklanmalı"*), `<job_id>:<platform>` anahtarıyla tekilleştiriliyor, böylece aynı hafta iki kez rapor çekmek mükerrer satır üretmiyor. `topic_performance()` ve `best_hooks()` toplulaştırma sağlıyor.
2. **`analytics.py`** artık ölçtüğü her metriği deftere yazıyor. Defter yazımı raporu asla düşürmüyor (yutuluyor): rapor insan için, defter makine için.
3. **`topics.py`** performansa göre sıralıyor — ama **yumuşak**: en az 2 video şartı aranıyor, böylece tek videonun şansı sıralamayı belirlemiyor. Ölçülmemiş konu da açlıkta kalmıyor.

`analytics_memory` iki kaynağı birleştiriyor: operatörün elle işaretlediği hook'lar + ölçülmüş performanstan türetilenler. Ayrıca `store_winning_hook` artık atomik yazıyor — kilitsiz oku-değiştir-yaz deseni paylaşılan `jsonstore` ölçümünde 40 kayıttan 35'ini kaybediyordu.

**Uçtan uca ölçüm** (iki video, sahte YouTube yanıtları):

| Adım | Sonuç |
|---|---|
| Önce: prompt eki | **0 karakter** |
| Rapor çekilince defter | **2 kayıt** yazıldı |
| Sonra: prompt eki | **229 karakter**, en iyi hook içinde |
| Konu performansı | `Uzay: 1200`, `Deniz: 80` |
| Konu seçimi | havuz `Deniz, Uzay, Yeni` → seçilen **`Uzay`** |

Geriye dönük uyum korundu: defter yokken `select_next_topic` eskisi gibi giriş sırasını döndürüyor (bir test bunu kilitliyor).

### 25. CI ilk kez gerçekten koştu: ffmpeg yoktu (2026-10-31)

Yol haritası 17 turdur "CI var" diyordu ama **hiç push edilmemişti**. `origin/cursor/hybrid-flux-architecture` son olarak `15b4c52`'de duruyordu; 50+ commit yalnızca yerelde vardı. Yani `.github/workflows/ci.yml` hiçbir zaman bir GitHub runner'ında çalışmamıştı.

Push edilince ne oldu:

| Koşu | Sonuç |
|---|---|
| `41228709572` (ilk gerçek CI) | ❌ `test` kırıldı — **15 test** `FileNotFoundError: 'ffmpeg'` |
| `41237050980` (düzeltme sonrası) | ✅ **success** — 732 passed, 3 skipped |

**Kök neden kod değil, CI dosyasının kendisiydi.** `ci.yml` şu yorumu taşıyordu:

> `# ffmpeg/ffprobe are preinstalled on ubuntu-latest`

Bu **yanlıştı**. Ve 17 tur boyunca "726 passed" diyen hiçbir koşu bunu göstermedi, çünkü yerel makinede ffmpeg PATH'te. Bu, CI'ın neden var olduğunun en net kanıtı: yerel yeşil, ortam farkını ölçmüyor.

Düzeltme iki parça:

1. **`ci.yml`** artık `apt-get install ffmpeg` çalıştırıyor ve `ffmpeg -version` / `ffprobe -version` basıyor — kurulum bir gün bozulursa iş **yüksek sesle** düşsün, sessizce testlere sızmasın.
2. **`tests/conftest.py`** tek bir `HAS_FFMPEG` bayrağı + saf `needs_ffmpeg(nodeid)` yüklemi kazandı. ffmpeg yoksa 15 etkilenen dosya `"ffmpeg/ffprobe not installed"` sebebiyle **skip** oluyor; ham traceback operatöre "kod bozuk" gibi görünmüyor.

Kapı listesi bilinçli olarak **dar**: yalnızca koşunun `FAILED tests/...` satırlarında adı geçen dosyalar. `test_ffmpeg_guard.py` iki yönü de sabitliyor — kapılı dosyalar skip olmalı, mock'lanmış/saf-mantık testleri **koşmaya devam etmeli**. `test_ffmpeg_guard_behavior.py` ise `shutil.which`'i `None`'a çeken bir pytest eklentisiyle skip'i *varsaymıyor, kanıtlıyor*.

**Yanlış dönüş (kayda değer):** guard'ı ilk olarak `PATH=""` ile alt süreçte sınamaya çalıştım. Python PATH'siz başlayamadı, koşu **41 dakika** asıldı ve alakasız bir `AttributeError` ile düştü (o da ayrı bir hatamdı: `publish_quality` modül düzeyinde `shutil` import etmiyor). Kararı saf bir fonksiyona taşıyıp süreç-içi eklentiye geçince 5 saniyeye indi.

**Kalan gerçek risk (P0, kanıtlandı):** Git geçmişinde `video-output/tiktok_session/` altında **1015 dosya** var — `Login Data`, `Network/Cookies`, `Local State` dahil. `644196f` bunları ağaçtan temizledi ve `.gitignore` tekrarını engelliyor, ama **geçmişten silmedi**. Ayrıca bu dosyalar zaten `origin` geçmişinde de var (`b3d6b74` ile), yani push yeni bir sızıntı yaratmadı — mevcut olanı görünür kıldı. Yapılması gereken: TikTok oturum çerezlerini geçersiz kılmak (hesap şifresi değişimi / tüm cihazlardan çıkış), sonra geçmişi `git filter-repo` ile temizlemek. `backups/otomasyon-yedek-2026-09-05.tar.gz` de geçmişte ama içindeki `n8n-data.tar` tarandı: gömülü token bulunamadı.

### 26. Sır tarayıcısı kördü: geçmişi hiç görmüyordu (2026-10-31)

Madde 25 CI'ı yeşile çevirdikten sonra `secret-scan` işi "Temiz: 394 dosyada sır deseni bulunamadı" diyordu. Aynı anda geçmişte **1015 oturum dosyası** olduğu biliniyordu (madde 25'in P0'ı). İkisi birlikte doğru olamazdı — ölçtüm ve **üç ayrı körlük** buldum.

| # | Körlük | Kanıt |
|---|---|---|
| 1 | Geçmiş hiç taranmıyor | `tracked_files()` = `git ls-files`, yani yalnızca çalışma ağacı |
| 2 | `video-output` tamamen atlanıyor | `SKIP_DIR_PARTS` içindeydi; orada **88 izlenen dosya** var |
| 3 | Oturum dosyaları regex'e görünmez | Chromium `Cookies`/`Login Data` **SQLite/ikili**; içerik deseni asla eşleşmez |

Üçüncüsü en sinsi olanı: bu sınıf sızıntının tehlikesi içindeki `token="..."` metni değil, **dosyanın kendisidir**. Yani doğru dedektör içerik değil **yol** desenidir.

**Düzeltme.** `scripts/secret_scan.py` iki mod kazandı. Ağaç modu (varsayılan) artık `video-output`'u atlamıyor ve yol desenlerini de uyguluyor. Yeni `--history` modu tüm ref'lerdeki blob'ları gezip iki dedektör sınıfı çalıştırıyor: 9 yol deseni (`browser_cookies`, `browser_login_data`, `browser_local_state`, `browser_profile_dir`, `ssh_private_key`, `key_material`, `session_state`, `dotenv`, `browser_web_data`) ve mevcut içerik desenleri.

Maliyet ölçüldü, çünkü "geçmiş taraması yavaş olur" varsayımı CI'ı öldürürdü:

| Ölçüm | Sonuç |
|---|---|
| `rev-list --all --objects` | **0,1 s** — 1774 tekil blob |
| İçerik taraması (blob başına ayrı `git`) | dakikalar — **reddedildi** |
| İçerik taraması (`cat-file --batch`, tek süreç) | **2,3 s** |

**Rapor okunur kılınmak zorundaydı.** İlk sürüm 951 bulgu bastı: 940'ı aynı dizinin her dosyası, 7'si test fixture'ı. Operatör 940 satırı okuyamaz. Üç iyileştirme:
- **Dizin tekilleştirme:** `browser_profile_dir` eşleşmesi bir kez raporlanır (`939 dosya içeriyor`), tek tek hassas dosyalar ayrıca kalır.
- **Doğru bayrak:** ilk sürüm "dosya HEAD'de mi" diye bakıp 7 sahte fixture'ı `HEAD'de` işaretledi. Doğrusu **değerin** hâlâ orada olması; bayrak artık `HEAD'de` / `düzeltilmiş` / `sadece geçmişte`.
- **Sahte işaretleme:** sıralı alfabe içeren değerler `muhtemelen sahte` etiketi alır — susturulmaz, işaretlenir.

**Baseline: kullanışsız CI, olmayan CI'dır.** Geçmişteki sızıntı `git filter-repo` çalıştırılmadan silinemez; bu yüzden her koşuda kırmızı olurdu ve dünkü ffmpeg dersinin tekrarı olurdu. `scripts/secret_scan_baseline.json` bilinen bulguları kabul eder; **yeni** bulgu CI'ı kırar. Kabul listesi boşaltılabilir: geçmiş temizlendiğinde liste kendini yeniler.

Baseline anahtarı üçüncü bir hata doğurdu: anahtar `(desen, dosya)` iken `test_secret_scan.py` içindeki **üç ayrı** OpenAI değeri tek anahtar üretti — aynı dosyaya yeni bir anahtar eklenirse baseline onu sessizce yutardı. Anahtar artık değerin kısa SHA-256 özetini taşıyor (geri döndürülemez, baseline sır sızdırmaz).

**Uçtan uca kanıt (geçici depoda, gerçek geçmişe dokunmadan):**

| Adım | Beklenen | Sonuç |
|---|---|---|
| Temiz depo | 0 | 0 ✅ |
| Geçmişe `Cookies` + `Local State` ekle | 1 | 1 ✅ |
| Baseline'a kaydet, tekrar tara | 0 | 0 ✅ |
| İkinci, **farklı** sızıntı (`prod.env`) | 1 | 1 ✅ |
| Kabul edilmiş `Cookies` gürültü yapıyor mu | hayır | hayır ✅ |
| Dosyayı ağaçtan sil, geçmişte kalsın | 1 | 1 ✅ |

Bu test **kendi hatamı yakaladı**: `dotenv` desenim `(^|/)\.env$` idi, yani yalnızca tam `.env`. `prod.env` kaçtı (çıkış 0). Desen `\.env$` oldu.

**CI'ın en kritik satırı.** Yeni `history-scan` işi `actions/checkout` varsayılanıyla (shallow, derinlik 1) çalışsaydı tarama yalnızca son commit'i görür ve **her zaman "temiz" derdi** — yani düzelttiğim körlüğün birebir aynısı. Ölçtüm:

| Klon | Görünen blob | Sonuç |
|---|---|---|
| shallow (`--depth 1`) | 429 | **0 bulgu** — kör |
| tam | 1774 | **12 bulgu** — doğru |

Bu yüzden `fetch-depth: 0` zorunlu ve `ci.yml`'de yorumuyla duruyor.

**Sınırları (dürüst):** (a) Regex ve yol desenleri bilinen biçimleri yakalar; tanınmayan bir sır biçimi kaçar. (b) Baseline rotasyondan sonra da dolu kalırsa eski bulguları gizlemeye devam eder — bu yüzden `how_to_clear` alanı dosyanın içinde. (c) İkili dosyalarda içerik taranmaz (yalnızca yol); bu tasarım gereği.

Sonuç: **750 passed, 3 skipped** (önceki 732 + 18 yeni), yerelde ve CI'da aynı.

#### 26.1 CI bu işi iki kez kırdı — ve haklıydı (2026-10-31)

Bu maddeyi yazarken CI'ın değerini iki kez daha gördüm. İkisi de **yerelde yeşil, runner'da kırmızı** oldu:

**Koşu `41239608134` — her iki iş de düştü.** Sebep kendi yeni test dosyamdı. Kök neden öğretici: `tracked_files()` = `git ls-files` yalnızca **izlenen** dosyaları döndürüyordu. Dosyam o sırada *untracked* olduğu için yerel tarama "Temiz: 398 dosya" dedi; commit edip CI'a gidince içindeki literal `sk-...` fixture'ı görünür oldu ve `test` + `history-scan` birlikte kırıldı. **Yani commit öncesi çalışan bir kapı, hatayı ancak commit'ten sonra gösteriyordu** — kullanışsız.

Düzeltme: `scan_targets(root)` — `git ls-files --cached --others --exclude-standard`. Untracked ama ignore'lu olmayan dosyalar da taranıyor. Ayrıca `root` zorunlu: `git` süreç cwd'sinde çalışır, `main` ise dosyaları `root` altından okur; pytest cwd'si `video-worker` olduğu için bu ayrışma gerçek bir hataya dönüştü. Maliyet 396 → 763 dosya, **1,07 sn**.

**Aynı koşuda ikinci ders:** baseline'ı commit etmeden CI'a gittim. `scripts/secret_scan_baseline.json` yoksa tarayıcı her şeyi "yeni" sayar ve iş kırmızı olur — kabul mekanizması sadece yerelde çalışıyordu. İlk koşuda tam bu görüldü: `12 baseline'da kabul edilmiş` yerine yerelde 0.

**Koşu `41240417309` — üç iş de yeşil:**

| İş | Süre | Sonuç |
|---|---|---|
| `secret-scan` | 7 s | ✅ |
| `test` | 1 m 31 s | ✅ 750 passed, 3 skipped |
| `history-scan` | 9 s | ✅ 14 bulgu, 14 baseline'da kabul, 0 yeni |

`history-scan` logunda **14 bulgu** görünmesi kritik: shallow klonda 0 görünüyordu. Yani `fetch-depth: 0` runner'da gerçekten yük taşıyor, tarama simüle edilmiyor.

### 27. İki sessiz çökme ve hiç olmayan lint kapısı (2026-10-31)

Madde 26'yı bitirdikten sonra `ruff` ile depoyu taradım — ve **prod'da çalışmayan iki kod yolu** buldum. İkisi de `SyntaxError` değil, yani `pytest` toplama aşaması onları görmedi; ikisi de yalnızca belirli bir kullanıcı eyleminde tetikleniyordu.

**Çökme 1 — `scripts/daily_autonomous_agent.py`: `--director` hiç çalışmadı.**

CLI bayrağı `execute_daily_run(director_mode=args.director)` çağırıyordu, ama imza `async def execute_daily_run(use_trend: bool = False):` idi:

```
TypeError: execute_daily_run() got an unexpected keyword argument 'director_mode'
```

Yani günlük ajanın "yönetmen modu" — madde 24'te üzerine kurulan geri besleme döngüsünün giriş noktası — her çağrıldığında anında ölüyordu. Cron'da bu, sessizce hiç video üretilmemesi demek.

**Çökme 2 — `app/telegram_bot.py`: tanımsız `pending_path`.**

`intent == "generate_video"` dalı, dosyanın hiçbir yerinde tanımlanmayan `pending_path`'i `.is_file()` ile okuyordu:

```
NameError: name 'pending_path' is not defined
```

Operatör Telegram'dan "yeni video yap" yazdığında bot çöküyordu. Dosyanın diğer dört dalı (`approve`/`reject`/`status`/`ideas`) doğru API'yi — `job_store.read_pending_payload(media_dir)` — kullanıyordu; yalnızca bu dal geride kalmıştı. Üstelik etrafındaki `try/except Exception: pass` bu hatayı **yutacaktı**, yani kullanıcı hata mesajı bile görmeyecekti.

#### Neden ikisi de CI'dan geçti

`ruff` `video-worker/requirements.txt` içinde **yoktu**. Kurulu olduğu için tesadüfen yerelde bulundular. Yani kapı yoktu — sadece şans vardı.

Ölçüm: `--select E9,F63,F7,F82` (yalnızca "bu kod çalışmaz" sınıfı) depoda **0 ihlal** veriyor. Stil kuralları (`E501`, `I001`…) ise 1000'i aşkın ihlal verirdi; onları eklemek kapıyı gürültüye boğup gerçek hatayı gizlerdi. Bu yüzden kural kümesi bilinçli olarak dar tutuldu.

| Kapı | Kapsam | Sonuç |
|---|---|---|
| `ruff --select E9,F63,F7,F82` | `video-worker/app`, `video-worker/tests`, `scripts` | 0 ihlal |
| `ruff --select B023` | `video-worker/app`, `scripts` | 0 ihlal (1 düzeltme sonrası; aşağıda) |

`ci.yml`'e `lint` işi eklendi (`ruff==0.16.5`, `--isolated`). `--isolated` şart: geliştiricinin makinesindeki `ruff.toml` sonucu değiştirirse "yerelde geçti, CI'da kaldı" olur — bu depoda bu tuzağa zaten düşülmüştü.

#### Üçüncü bulgu — `B023`: geç bağlanan döngü değişkeni

`documentary_v2/director/pipeline.py` içinde `_pool_sort_key` döngü gövdesinde tanımlanıp `prefer_video`'yu serbest değişken olarak yakalıyordu. Bugün zararsız (`sorted` onu hemen çağırıyor), ama fonksiyon döngü dışına taşındığı an sessizce **son** iterasyonun değerini kullanırdı. Parametre olarak bağlandı: `prefer_video: bool = prefer_video`.

#### Regresyon kilidi — ve kilidin kilidi

`tests/test_natural_message_crashes.py` (4 test) eklendi. Çökmeleri yeniden üretmek pahalı olduğu için iki yaklaşım birlikte kullanıldı:

- `pending_path`: gerçek çağrı, `tmp_path` + stub `send_message` ile. Hatayı geri koyunca test **gerçekten** `NameError: name 'pending_path' is not defined` ile düştü — doğrulandı.
- `director_mode`: gerçek çağrı video üretip yayınlar, testte koşulamaz. Bunun yerine AST ile **imza ↔ çağrı** karşılaştırılıyor. Parametre silinince test `AssertionError: imzada olmayan argüman: {'director_mode'}` verdi — doğrulandı.

Yani testler sadece "geçmiyor", hata geri gelince düşüyor. Bu ayrımı yapmadan yazılan test, hiçbir şeyi kilitlemez.

**Sınır (dürüst):** `scripts/` altındaki `daily_autonomous_agent.py` hâlâ tam kapsanmıyor. Gerçek birim testi `execute_daily_run`'ın yan etkilerini (render, yayın, Telegram) teker teker sarmalamayı gerektirir; bugün yalnızca imza/çağrı tutarlılığı ve CLI argüman ayrıştırması kilitli. Ajanın iç mantığı hâlâ test edilmiyor.

Sonuç: **754 passed, 3 skipped** (madde 26'daki 750 + 4 yeni), yerelde 1 m 57 s.


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
| `3af7cc5` | Sahte zaman aşımı düzeltildi; tamamlanan yükleme okunuyor (2 dosya) |
| `efa6e56` | Bütçe yayıncı timeout'larıyla hizalandı + sözleşme testi (2 dosya) |
| `52a0f85` | `append_publish_log` kilit + atomik yazma (2 dosya) |
| `7edd883` | Konu seçimi kilidi + paylaşılan `jsonstore` (5 dosya) |
| `417863f` | `/generate` guard'ı atomik; ikinci eşzamanlı üretim engellendi (5 dosya) |
| `ce6b93e` | `/publish` bilinmeyen-iş dalı atomik (koşullu INSERT) + çökmede `failed` (3 dosya) |
| `de4c4d7` | Eşzamanlı silmede geçici `WinError 5` retry'ı (1 dosya) |
| `77f1c51` | Unlink retry + çökme bırakma testleri (1 dosya) |
| `3181eb7` | Kapı testi `frozenset` sırasına bağımlı olmaktan çıkarıldı (1 dosya) |
| `08ae6e1` | Dış ağ engeli + test retry politikası sıfırlandı; paket 50 sn (2 dosya) |
| `3fa5e80` | Bu belgeye madde 20 (dış ağ sızıntısı) |
| `d9317c1` | CI yorumundaki doğrulanmış test sayısı güncellendi (1 dosya) |
| `c355820` | Madde 20 ölçüm tablosu + commit günlüğü |
| `1a5b777` | Yayın → iş → manifest zinciri (madde 21, 6 dosya) |
| `cd7628c` | Yayın öncesi kalite kapısı + CI secret scan (madde 22, 10 dosya) |
| `31ec209` | Secret scan test fixture'ları runtime'da kuruluyor (1 dosya) |
| `557e7ef` | Timeout sonrası durum sorgusu: inflight + TikTok/YouTube API (madde 23, 7 dosya) |
| `386eb3d` | Madde 23 ölçüm tablosu + commit günlüğü |
| `5d79d43` | Analitik → üretim geri besleme döngüsü (madde 24, 4 yeni/6 dosya) |
| `24cd5e0` | CI ffmpeg kurulumu + ffmpeg kapılı testler açık sebeple atlanıyor (madde 25) |
| `cf03d0a` | Madde 25 ölçüm tablosu + CI yorumları güncel sayılarla |
| `43064ca` | Lint temizliği: kullanılmayan import/değişken (CI yeşil #3) |
| `96ca81e` | Sır tarayıcısına `--history` modu + baseline + CI `history-scan` işi (madde 26) |
| `593ec70` | Untracked dosyalar da taranıyor: commit öncesi kapı gerçekten çalışıyor |
| `f327239` | Bayat sayılar ölçümle hizalandı (test süresi, tarama süresi) |

> Bu belgeyi güncelleyen commit ayrıca `docs:` önekiyle geçmişte bulunabilir (kendi hash'ini içeremez).

> `6fbee82` zorunluydu: commit edilen `app/pipeline.py`, `app/documentary_v2/__init__.py` ve `pipeline_mode.py`'yi import ediyordu ama bunlar hiç commit edilmemişti. Taze klon import aşamasında patlıyordu, yani CI eklenemezdi.
