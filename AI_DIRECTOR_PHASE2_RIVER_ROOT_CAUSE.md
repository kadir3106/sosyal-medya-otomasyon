# AI Director Phase 2 — River Root Cause (forensic)

**Durum:** Kod yazılmadı. Büyük refactor yok. Phase 3’e geçilmedi. Onay bekleniyor.  
**Kaynak job:** `20260922-190245` (Phase 2 Rolex smoke)  
**Kanıt:** `video-output/phase2_smoke_dump.json`, `director_gate.py`, `stock_media.extract_proper_phrases`, `subtitles.write_ass`, `pipeline.py` Hook Director rewrite.

---

## Executive verdict

Akarsu **Phase 1 “query self-score” bug’ından değil**; metadata skorlanıyor.  
Kabul sebebi: **sahte entity `"Every"`** + **substring entity match** (`"every" in tags`) + **semantic conflict yok** + **clip reuse** (Hans/MISS beat’lerde aynı river klibi timeline’da tekrarlanır).

Bakery blacklist’e `river` eklemek **yanlış çözüm**. Regression fixture olarak river/bakery kalmalı; genel mekanizma semantic conflict + entity hygiene olmalı.

---

## 1) River asset forensic chain (gerçek dump)

### Accept edilen beat (asset seçiminin olduğu yer)

| Alan | Değer (dump) |
|------|----------------|
| **spoken_span** | `Every billion in profit gets reinvested or donated tax-free.` |
| **visual_beat index** | scene_index **3** (word_to_visual beat #3) |
| **concept** | `tax_document` |
| **narrative_role** | `document` |
| **entities / must_show** | **`["Every"]`** ← kök bug |
| **visual_intent** | Document / tax / legal mechanism visual — not generic office filler |
| **search_queries (plan)** | `legal tax documents paperwork`, `corporate filing exemption documents` |
| **enrich sonrası query (accept denemesi)** | `Rolex Foundation Every Secret How owned 100% private` |
| **provider** | **pixabay** |
| **asset_id** | **14053** |
| **candidate metadata** | `title=""`, `tags="hometown, brook, and every flower, stream, river, streams, nature, landscape, the rural brook, cool, autumn, creek, morning"`, `url=https://pixabay.com/videos/id-14053/` |
| **relevance_score** | **0.479** (reproduce: ~0.529 with same need) |
| **entity_score** | **1.0** |
| **gate decision** | **`accepted`** (`gate_reason: accepted`) |
| **selected path** | `/data/media/work/20260922-190245/clip_1.mp4` |

Aynı dump’ta Hans Wilsdorf beat (#1) **255 reject / MISS** — river **o beat’te accept edilmedi**.

### Neden ekranda “doesn't have shareholders / Hans…” altında görünüyor?

Director yalnız **3 clip** üretti (`clip_count=3`, `scene_count=8`, `clip_reuse_ratio=2.67`):

| clip | asset | beat kaynağı |
|------|--------|----------------|
| `clip_0` | Pexels photo Rolex+petals `38043383` | beat 0 (Rolex tax line) |
| `clip_1` | **Pixabay river `14053`** | **beat 3 (“Every billion…”) — yanlış ACCEPT** |
| `clip_2` | aynı Rolex photo | beat 7 |

Render `build_scene_sources` ile 3 klibi 8 sahneye yayar. Smoke video ffprobe süresi ~**5.0s**; yeniden kurulan schedule’da river yaklaşık:

| Timeline | Asset |
|----------|--------|
| 0.00–1.60s | Rolex (clip_0) |
| **1.20–2.80s** | **river (clip_1)** |
| 2.40–4.00s | Rolex (clip_2) |
| 3.60–5.00s | Rolex reuse |

Bu, izleyicinin **~1–4s akarsu** gözlemiyle örtüşür. VO o sırada shareholders / Hans anlatıyor olsa bile görüntü **Hans beat’inin seçimi değil**; **yanlış accept edilmiş clip_1 + miss’lerden gelen reuse**.

---

## 2) Gate gerçekten neyi değerlendiriyor? (kanıtlı)

### Metadata yeterli miydi?

**Evet — ve açıkça doğa/akarsu.**  
Tags: `brook, stream, river, nature, landscape, creek…`  
Boş metadata değil. Phase 1 `no_asset_metadata` yolu tetiklenmedi.

### Neden financial/entity beat’te REJECT olmadı?

`evaluate_asset` (`director_gate.py`):

1. Forbidden list → `river`/`nature` **yok** (bilinçli; bakery-style kelime yaması yok).
2. `required_entities = ["Every"]`
3. Entity hit: `e.lower() in blob_low` → **`"every" in "… and every flower …"`** → **hit**
4. `entity_score = 1.0`
5. Topical (query tokens ∩ blob tokens): `"every"` overlap → topical ~0.14
6. `relevance = 0.55*topical + 0.45*1.0 ≈ 0.48–0.53` ≥ `_ENTITY_MIN (0.45)` → **ACCEPT**

**Reproduce (aynı metadata + aynı need):**

```
accepted True  rel≈0.53  ent=1.0  reason=accepted
```

**Aynı river, gerçek entity need** (`Hans Wilsdorf`, `Rolex`, `Foundation`):

```
accepted False  reason=missing_required_entities  ent=0.0
```

Yani gate, **doğru entity listesi** ile river’ı reddediyor. Smoke’ta problem **need’in kirlenmesi**.

### Unknown relevance ≠ relevant?

Bugün: metadata dolu + sahte entity substring hit → “bilinen ama yanlış” ACCEPT.  
Eksik olan: **intent/semantik uyum** ve **entity kanıt kalitesi** (tek stopword/cümle başı kelime entity sayılmamalı; incidental substring yetmemeli).

---

## 3) Root causes (öncelik sırası)

### RC1 — Sahte entity: `"Every"` (heuristic NER)

```text
extract_proper_phrases("Every billion in profit…") → ["Every"]
```

`"every"` `_STOPWORDS` / `_TITLE_NOISE` içinde **değil**. Cümle başı Capital → proper-phrase sanılıyor.

Aynı aile:

- `No Wall Street…` → `["Wall","Street"]` (Hans Wilsdorf query’ye rağmen entity need bozuluyor)
- `Hans Wilsdorf…` → `["Hans","Wilsdorf","Swiss"]` (phrase birleşik tutulmuyor — ayrı sorun)

### RC2 — Entity match çok gevşek (substring)

```python
entity_hits = sum(1 for e in entities if e.lower() in blob_low)
```

`"every" ∈ "every flower"` → false positive.  
Phrase-boundary / token-level match yok.

### RC3 — Semantic conflict yok

Beat intent: tax / ownership / billion profit.  
Asset concept: river / nature / landscape.  
Gate yalnız: forbidden tokens + entity substring + topical token overlap.  
**Çelişen kavram kümeleri** (ownership/finance vs nature/water) ölçülmüyor.

### RC4 — Clip reuse, miss’leri “yanlış anda yanlış görüntü” yapıyor

Hans beat MISS (gate doğru çalıştı, AI max=0).  
Render yine de river klibini timeline’a serpiyor → VO–görüntü desync.

### RC5 — LLM storyboard düştü (bağlam)

Smoke log: LLM geçerli Director JSON üretti; `script_gen._parse` **`script` key** aradığı için reject → **heuristic**.  
Heuristic RC1’i üretti. (Düzeltme onaysız; root cause notu.)

---

## 4) Caption ~3s gecikme — kod değiştirmeden neden

**Birincil neden: Hook Director karaoke suppression (bilinçli Phase 2 davranışı).**

Dump:

```json
"hook_director": {
  "overlay_text": "The Rolex Foundation Secret:",
  "hook_seconds": 1.8,
  "karaoke_start_seconds": 1.8,
  ...
}
```

`pipeline.py` Director dalında ASS yeniden yazılırken:

```python
karaoke_start_seconds=karaoke_start  # 1.8
```

`subtitles.write_ass`:

- `cue_end <= karaoke_start_ticks` → karaoke satırı **atılır**
- aksi halde start **1.8s’e clamp**

VO sıfırdan başlar; dinamik caption **en erken ~1.8s**.  
İlk görünen karaoke grubu kelime sınırına göre **~2–3s** civarına kayabilir → kullanıcının “~3 sn” gözlemi.

| Hipotez | Sonuç |
|---------|--------|
| TTS timestamps eksik | **Hayır** (elevenlabs; word_boundaries var, aksi karaoke hiç olmazdı) |
| subtitle generation bozuk | **Hayır** (gecikme parametreli) |
| **hook suppression** | **Evet — birincil** |
| visual-beat timing | **Hayır** (ASS beat timeline’ına bağlı değil) |
| render offset | **Kanıt yok**; ASS 0’dan yazılıyor |

**Not:** Overlay ile karaoke çakışmasını önlemek doğru hedef; ama 1.8–3s sessiz karaoke + kısa punch, “caption geç geldi” hissi yaratıyor. Fix tasarımı onay sonrası (ör. punch bitince hemen karaoke; veya punch süresini kısalt).

---

## 5) Audio (Phase 3 issue — dokunulmadı)

Videoda vokalli BGM ile narration çakışması gözlemlendi.  
**Phase 3 kaydı:** voice-over altında lyrical/vocal BGM yasak; instrumental/dark-luxury/ambient + ducking sonra.

---

## 6) Minimal ama genel çözüm tasarımı (henüz uygulanmadı)

Öncelik: **semantic relevance > entity accuracy > storytelling > pacing > variety**.  
`river`/`bakery` yalnız **regression fixture**.

### A) Entity hygiene (küçük, yüksek etki)

- Stopword / sentence-starter filter: `Every`, `This`, `That`, `No`, … entity olamaz.
- Multi-word person/brand: `Hans Wilsdorf` tek entity.
- Entity match: **word-boundary / token**, ham substring değil.

### B) Semantic conflict gate (genel mekanizma)

Beat’ten **expected concept families** (ownership, person_archive, finance, place_geneva, product_watch…).  
Asset metadata’dan **observed families** (nature_water, food_bakery, sports…).  
Hard conflict → **REJECT** (blacklist yaması değil, aile çatışması).  
Örnek: `ownership|finance|person` vs `nature_water|landscape` → conflict.

### C) Entity-specific strictness / ladder

Gerçek kişi/marka beat’inde:

`exact entity → archive/photo → entity+context → document/location → controlled conceptual → AI`  

**Random generic stock fallback yasak.** Miss > yanlış river.

### D) Intent evidence

Tax/document beat’te asset blob’da tax/document/ownership kanıtı yoksa entity tek başına yetmez (özellikle tek zayıf token).

### E) Caption (ayrı, küçük)

Hook punch ile karaoke delay’i gözden geçir; VO ile ilk kelimelerin görünürlüğünü ölç. Audio pipeline’a dokunma.

### F) LLM storyboard parse (ayrı ticket)

Director JSON için `script` zorunlu kılan `_parse` kullanılmamalı — heuristic’e düşüş RC1’i besliyor.

---

## 7) Eklenecek regression testleri (plan)

| Test | Girdi | Beklenen |
|------|--------|----------|
| **River / shareholders-Hans** | spoken: doesn't have shareholders / Hans Wilsdorf / foundation; candidate tags: river/stream/rocks/nature/landscape | **MUST REJECT** via `evaluate_asset` (gerçek acceptance pipeline) |
| **Bakery** | mevcut Foundation need + bakery metadata | **MUST REJECT** (yeşil kalsın) |
| **Every≠entity** | `"Every billion…"` → entities must not be `["Every"]` **veya** river tags ile Every-need ACCEPT olmamalı | fail-closed |
| **Substring trap** | entity `"Every"` + tags `every flower, river` | reject / no entity_score=1.0 on incidental word |
| **Positive control** | Hans Wilsdorf + archive portrait metadata | ACCEPT (entity-specific) |

---

## 8) Cevap özeti (istenen maddeler)

| Soru | Cevap |
|------|--------|
| **River neden geçti?** | Beat #3 need entity=`Every`; Pixabay tags’te `every flower` + river; substring hit → entity_score=1.0 → relevance≥0.45 → ACCEPT. Sonra clip reuse ile ~1.2–2.8s ekranda. |
| **Hangi gate eksik?** | (1) Entity hygiene, (2) boundary-safe entity match, (3) semantic conflict (finance/ownership vs nature), (4) intent evidence. Metadata boş değildi. |
| **Caption neden geç?** | `karaoke_start_seconds=1.8` Hook Director suppression — TTS/render değil. |
| **Minimal genel çözüm?** | Entity hygiene + token match + concept-family conflict; river/bakery fixture. Blacklist’e river ekleme. |
| **Regression?** | River MUST REJECT; bakery yeşil; Every-trap; positive Wilsdorf. |

---

## Onay kapısı

Root cause **kanıtlandı**. Büyük refactor yok.  
İmplementasyon + testler için **onayını bekliyorum**. Phase 3’e geçilmedi.
