# AI Director Phase 2 — Real Smoke (Rolex)

**Tarih:** 2026-09-22  
**Job:** `20260922-190245`  
**Konu:** The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders  
**Amaç:** `DIRECTOR_ENABLED=true` üretim; **yayın yok**; Telegram / pending approval’da dur.  
**Video (host):** [`video-output/AI_DIRECTOR_PHASE2_ROLEX_SMOKE_20260922-190245.mp4`](video-output/AI_DIRECTOR_PHASE2_ROLEX_SMOKE_20260922-190245.mp4)  
**Video (container):** `/data/media/20260922-190245.mp4`  
**Karar dump:** [`video-output/phase2_smoke_dump.json`](video-output/phase2_smoke_dump.json)

---

## Sonuç özeti (izleme için)

| Madde | Değer |
|--------|--------|
| State | `pending.json` mevcut → **awaiting approval** (publish yok) |
| `quality.engine` | **director** |
| TTS | elevenlabs |
| Hook overlay | `The Rolex Foundation Secret:` (≤6 kelime) |
| Karaoke delay | `1.8s` (= hook_seconds) |
| Visual beats planlanan | 8 |
| Selected asset olan beat | **3 / 8** |
| Miss (gated, no fill) | **5 / 8** |
| `clip_count` / `scene_count` | 3 / 8 |
| `clip_reuse_ratio` | **2.67** (quality warning: `clip_reuse_ratio_high`) |
| AI image | **0** (`DIRECTOR_AI_IMAGE_MAX=0` — Fal 403’ü bypass; düzeltilmedi) |
| Planner | LLM storyboard üretildi ama parser `script` key beklediği için **reject → heuristic** |

**İlk deneme notu:** Host shell’de `DIRECTOR_ENABLED=false` .env’i eziyordu → legacy stock job `20260922-183402` üretildi ve **discard** edildi. Bu rapor yalnızca Director job `20260922-190245` içindir.

---

## Word-to-visual zinciri (kaydedilen)

Kaynak: `pending.quality.word_to_visual`

| # | spoken_span (kısa) | concept / entities | search queries | rejected | selected | rel / ent / conf | duration |
|---|--------------------|--------------------|----------------|----------|----------|------------------|----------|
| 0 | Rolex… zero corporate income tax | tax_document / Rolex | legal tax documents… | 0 | **pexels_photo 38043383** — Rolex watch in pale petals | 0.48 / 1.0 / 0.55 | 1.6s |
| 1 | Hans Wilsdorf… Swiss foundation | location / Foundation,Swiss,Hans,Wilsdorf | Swiss cityscape, Swiss landmark | **255** | **MISS** | 0 / 0 / 0.55 | 1.6s |
| 2 | No Wall Street suits… | founder_archive / Wall,Street | Wall; Hans Wilsdorf portrait archive | **143** | **MISS** | 0 / 0 / 0.55 | 1.6s |
| 3 | Every billion… tax-free | tax_document / Every | legal tax documents… | 77 | **pixabay 14053** — nature stream / flowers (“every…”) | 0.48 / 1.0 / 0.55 | 1.6s |
| 4 | Amateurs buy watches… | Amateurs / Amateurs | Amateurs + topic | 80 | **MISS** | 0 / 0 / 0.55 | 1.6s |
| 5 | elite founders build… trusts | detail / (topic string) | spoken + topic | 48 | **MISS** | 0 / 0 / 0.4 | 1.6s |
| 6 | That’s why… | detail / (topic string) | spoken + topic | 48 | **MISS** | 0 / 0 / 0.4 | 1.6s |
| 7 | Rolex… income tax (tekrar) | tax_document / Rolex | legal tax documents… | 0 | **pexels_photo 38043383** (aynı #0) | 0.48 / 1.0 / 0.55 | 1.6s |

**Reject reason totals:** `missing_required_entities` 556 · `below_threshold` 74 · `forbidden_concept` 21  
**Foodish gate hits (örnek):** `cooking` (Ugandan “rolex” wrap), `cake` — reddedildi.

---

## Kontrol listesi

| # | Kontrol | Sonuç | Not |
|---|---------|--------|-----|
| 1 | Rolex → Rolex-specific arama | **Kısmen** | Beat 0/7 Rolex entity + tax query; seçilen kare Rolex ürün ama **çiçek yatağı** (tax/document intent değil) |
| 2 | Hans Wilsdorf → entity/archive | **Arama var, asset yok** | Beat 1/2 Wilsdorf query’leri denendi; 255+143 reject; AI kapalı → MISS (zorla generic yok) |
| 3 | Switzerland/Geneva konum | **Zayıf** | Beat 1 `Swiss cityscape/landmark` aradı ama entity gate yüzünden hepsi reject; seçim yok |
| 4 | money/billions/tax somutlaştırma | **Karışık** | Tax intent beat’lerde var; #3’te entity `"Every"` bug → **doğa/stream** seçildi (yanlış somutlaştırma) |
| 5 | bakery/food/cookie gate | **Geçti** | forbidden_concept + foodish örnekler reject |
| 6 | Tek generic 4–5 sn idle | **Süre olarak hayır** | Beat duration hep **1.6s**; fakat render’da 3 klip 8 sahneye **reuse 2.67** → pratikte aynı görüntü uzuyor |
| 7 | Visual beat videoya yansıyor mu? | **Zayıf** | 5/8 miss → timeline çoğunlukla 3 kabul edilen klibin tekrarı |
| 8 | Hook 0–3s daha güçlü mü? | **Plan evet** | Punch overlay kısa; hero_closeup planlı — izlemede doğrula |
| 9 | Hook overlay vs karaoke çakışma | **Plan: önlendi** | `karaoke_start_seconds=1.8` = hook end |
| 10 | Yanlış asset → zorla kullanmama | **Geçti (miss)** | Ungated fill yok; AI budget 0; miss tercih edildi |

---

## Operasyon notları (kod değişikliği yok)

1. **Host env override:** Windows session `DIRECTOR_ENABLED=false` compose `.env=true` değerini eziyor. Smoke için `$env:DIRECTOR_ENABLED='true'` ile recreate şart.  
2. **Fal 403:** İlk Director koşusunda AI fallback → hard fail. Bu smoke’ta `DIRECTOR_AI_IMAGE_MAX=0` ile atlandı (Fal düzeltilmedi).  
3. **LLM storyboard kaybı:** Router geçerli Director JSON üretti; `script_gen._parse` `script` key aradığı için “heuristic storyboard”a düşüldü. (Düzeltme bu smoke kapsamında yapılmadı.)  
4. **Heuristic entity noise:** `Wall`/`Street`, `Every`, `Amateurs` gibi yanlış entity’ler retrieval’ı bozuyor.

---

## Hook Director

```json
{
  "overlay_text": "The Rolex Foundation Secret:",
  "hook_seconds": 1.8,
  "karaoke_start_seconds": 1.8,
  "hero_shot": "hero_closeup",
  "motion": "slow_push"
}
```

Script hook (karaoke metni, gecikmeli): *Rolex doesn’t have shareholders, and it pays zero corporate income tax.*  
→ Overlay ile aynı anda aynı paragraf tekrarlanmamalı (plan).

---

## Yayın

**Yapılmadı.** Pending approval’da bırakıldı. Telegram’dan onaylama/yayınlama bu testin parçası değil.

---

## İzleme odaklı verdict

Sistem **gate + miss** davranışını koruyor (bakery/food reject, ungated fill yok).  
Ama bu koşuda **görsel anlatım kalitesi zayıf:** az kabul, yüksek clip reuse, Wilsdorf/Geneva boş, tax beat’lerde alakasız seçimler (çiçek / doğa).  

**Doğru görüntü → doğru anda → yeterince hızlı → premium kurgu** hedefine bu smoke **henüz ulaşmıyor** — özellikle LLM storyboard’un heuristic’e düşmesi ve AI fallback’in kapalı olmasıyla.

Phase 3 audio/pacing **başlatılmadı.**

---

*Dump + video host `video-output/` altında. Pending container `/data/media/pending.json`.*
