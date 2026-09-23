# AI Director Rolex — kontrollü entegrasyon testi

**Tarih:** 2026-09-22 (UTC job `20260922-172434`)  
**Konu:** Rolex  
**Amaç:** `DIRECTOR_ENABLED=true` ile üretim; **yayın yok**; Telegram/onay aşamasına kadar.  
**Sonuç özeti:** Üretim tamamlandı → `awaiting_approval`. Publish çağrılmadı. Test sonrası `DIRECTOR_ENABLED=false`.

---

## Ortam

| Madde | Değer |
|--------|--------|
| Job ID | `20260922-172434` |
| Video | `/data/media/20260922-172434.mp4` (Docker volume `shared-media`) |
| `quality.engine` | `director` |
| TTS | elevenlabs |
| Sahne sayısı | 8 |
| `stock_cache_reuse_ratio` | 0.0 |
| Job state (son) | `awaiting_approval` |
| Publish | **yapılmadı** |
| Test sonrası flag | `DIRECTOR_ENABLED=false` (doğrulandı) |

**Not:** Eski casino pending kilidi test için `pending.pre_rolex_director_test.json` yedeğine alındı + `jobs.clear_awaiting` (yayın değil, sadece kilit açma).

---

## Planner yolu

1. Primary model `google/gemma-4-31b-it:free` → AI router **HTTP 400** (beklenen airouter uyumsuzluğu).
2. Fallback `gemini-flash` → AI router **çok sayıda 502**.
3. Log: `Director planner LLM failed …; heuristic plan`
4. Yani bu koşuda **yaratıcı plan LLM değil, heuristic** kullanıldı (script `visual_prompts` / stock query’lerden). Refactor yapılmadı; aşağıda öneri var.

---

## Sahne kararları (log `director_clips_ready` + `pending.quality`)

| # | scene_type | visual_intent (kısa) | MediaKind | query | provider | score | accepted |
|---|------------|----------------------|-----------|-------|----------|-------|----------|
| 0 | hook | Rolex crown / green leather macro | **stock_video** | Rolex corporate legal tax exemption documents | pexels | 1.0 | yes |
| 1 | evidence | Swiss vault door Geneva | **stock_video** | Rolex Swiss bank vault steel door gold bars | pexels | 1.0 | yes |
| 2 | evidence | Watchmaker loupe / Submariner movement | **stock_photo** | Rolex watchmaker loupe mechanical watch movement | pexels_photo | 1.0 | yes |
| 3 | evidence | Empty boutique display case | **stock_video** | Rolex boutique empty display case | pexels | 1.0 | yes |
| 4 | evidence | Executive / Daytona boardroom | **stock_video** | Rolex boardroom meeting executive wearing watch | pexels | 1.0 | yes |
| 5 | evidence | Watchmaker assembly bench | **stock_photo** | Rolex watchmaker swiss watch assembly bench | pexels_photo | 1.0 | yes |
| 6 | evidence | Hans Wilsdorf foundation | **stock_video** | Rolex hans wilsdorf foundation | pexels | 1.0 | yes |
| 7 | evidence | Swiss vault | **stock_video** | Rolex swiss vault | pexels | 1.0 | yes |

### Plan’daki preferred_kinds (heuristic `director_plan`)

- Çoğu sahne: `stock_video`, `stock_photo`
- Sahne 2 ve 5: `stock_photo`, `stock_video`, `ai_image` + `allow_ai_generation: true`

### AI image

- `ai_image_used`: **0**
- Sahne 2 ve 5’te AI izinliydi ama **stock_photo bulundu** → AI’ye düşülmedi (beklenen free-first davranış).

### Fallback

- **Planner fallback:** LLM 400/502 → heuristic plan (neden: AI router erişim/model).
- **Sahne fill fallback:** kullanılmadı (`clip_count=8`, fill yok).
- **Medya kind fallback:** sahne 2/5’te video yerine photo kabul (plan sırasına uygun).

### Reddedilen adaylar

- Log’da **adetli reject listesi yok**. Kod şu an yalnızca kabul edilen meta’yı (`accepted` / son deneme) yazıyor; ara denemelerin `rejected` nedenleri persist edilmiyor.
- Bu yüzden “kaç aday reddedildi” bu testte ölçülemadi (aşağıdaki öneri).

---

## Kontrol listesi

| # | Kontrol | Sonuç |
|---|---------|--------|
| 5 | Rolex ile ilgisiz görüntü kabulü | **Belirsiz / zayıf doğrulama.** Tüm skorlar 1.0; skor çoğunlukla **query metninin kendisine** bakıyor, Pexels aday title/tags blob’una değil. Gerçek kare alaka için manuel izleme veya metadata skor düzeltmesi gerekir. |
| 6 | Hepsi `stock_video` değil | **Geçti** — 6× `stock_video`, 2× `stock_photo` |
| 7 | AI yalnız gerektiğinde | **Geçti** — AI image 0; izinli sahnelerde photo yeterli oldu |
| 8 | Legacy silinmedi | **Geçti** — flag kapatıldı, legacy dal kodda duruyor |
| 9 | Flag tekrar false | **Geçti** — container `DIRECTOR_ENABLED False` |
| 3 | Yayın yok | **Geçti** — state `awaiting_approval` |

**Genel:** Entegrasyon yolu çalıştı (Director flag → clip → render → pending). Planner LLM bu koşuda düştü; relevance telemetrisi yetersiz. Büyük refactor **yapılmadı**.

---

## Bulgular (onay bekleyen öneriler — uygulanmadı)

### 1) AI router model / erişim (planner)

- **Sorun:** `OPENROUTER_MODEL=google/gemma-4-31b-it:free` airouter’da 400; `gemini-flash` 502.
- **Dosya:** `.env` / AI router host; çağrı `script_gen._call_llm_with_fallback` ← `director_planner.plan_scenes`
- **Öneri:** Test için airouter-safe primary (`gemini-flash` / `smart` / çalışan combo); 502 ise AI router sağlığını ayrı kontrol. Director model seçmesin — env/AI router düzeltilsin.

### 2) Relevance skoru şişmesi

- **Sorun:** `director.py` stock sonrası skorda çoğu zaman query/topic string’i skorlanıyor → neredeyse her zaman ≥ eşik (1.0).
- **Dosya:** `video-worker/app/director.py` (`_try_kind` / `score_candidate_text` kullanımı)
- **Öneri:** Pexels/Pixabay adayının title/tags/description blob’unu skora ver; düşükse reddedip log’a `rejects[]` yaz. Onaysız refactor yok.

### 3) Reject telemetrisi eksik

- **Sorun:** İstenen “reddedilen adaylar ve nedenleri” raporu için veri yok.
- **Dosya:** `video-worker/app/director.py`
- **Öneri:** Sahne başına `attempts: [{kind, query, score, reject_reason}]` meta.

### 4) Heuristic plan LLM’siz

- Bu testte yaratıcı LLM planı çalışmadı; çeşitlilik heuristic’ten geldi. Asıl “AI Director düşünür” iddiası için (1) düzeltilmeden tekrar koşulmalı.

---

## Manuel sonraki adım (opsiyonel)

- Telegram’da `20260922-172434` videosunu izle; Rolex alaka kontrolü görsel.
- **Onaylama / yayınlama** bu testin parçası değil — Reddet veya beklet.
- İstersen (1)+(2)+(3) için ayrı onaydan sonra küçük patch.

---

*Legacy path değiştirilmedi. Publish edilmedi. DIRECTOR_ENABLED test sonunda false.*
