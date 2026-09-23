# AI Director Phase 2.1 — Entity Hygiene + Semantic Quality Gate

**Tarih:** 2026-09-23  
**Kapsam:** Phase 2.1 only (Phase 3 yok)  
**Smoke job:** `20260923-050839`  
**Konu:** The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders  
**Yayın:** yok (pending / Telegram approval)  
**Video (host):** [`video-output/director_phase21_rolex_smoke.mp4`](video-output/director_phase21_rolex_smoke.mp4)  
**Splitscreen:** [`video-output/director_phase21_rolex_smoke_splitscreen.mp4`](video-output/director_phase21_rolex_smoke_splitscreen.mp4)  
**Beat dump:** [`video-output/phase21_beats_summary.json`](video-output/phase21_beats_summary.json)

---

## Sonuç özeti

| Madde | Sonuç |
|--------|--------|
| Entity hygiene (`Every`/`The`/`Billions`) | **Geçti** — smoke entity listesinde yok |
| Token/phrase boundary (no `e in blob`) | **Geçti** — `every ∉ every flower` |
| Semantic concept-family conflict | **Geçti** — 51 `semantic_conflict` reject |
| Entity score alone ≠ ACCEPT | **Geçti** — finance+nature conflict reject |
| Unknown ≠ relevant / prefer miss | **Geçti** — Hans Wilsdorf + topic-string beat’ler MISS |
| River / nature / food final selected | **Yok** (selected metadata’da bad hit yok) |
| Caption karaoke from t≈0 | **Geçti** — pipeline `karaoke_start_seconds=0.0`; frame t=0.3’te karaoke görünür |
| Director unit/regression | **34 passed** |
| Full suite | **259 passed / 2 failed** (Fal AI visuals — external, bu phase’de düzeltilmedi) |

---

## Before / after scoring

### Phase 2 smoke RC (`20260922-190245`) — BEFORE

| Spoken / intent | Entity noise | Selected | Neden yanlış |
|-----------------|--------------|----------|--------------|
| Every billion… tax-free | **`Every`** false entity | Pixabay **river / every flower / nature** | `e.lower() in blob` → `every` ⊂ `every flower`; entity_score=1.0 → ACCEPT |
| Hans Wilsdorf… | Multi-token noise | MISS / reuse | Retrieval zayıf; sonra river reuse |
| Rolex tax | Rolex OK | Rolex-in-petals (tax intent zayıf) | Entity match tek başına yetiyordu |

Reject dağılımı (Phase 2): çoğunlukla `missing_required_entities` / `below_threshold`; **semantic family yok**.

### Phase 2.1 smoke (`20260923-050839`) — AFTER

| Spoken / beat | Entities (hygienized) | Gate | Selected |
|---------------|----------------------|------|----------|
| Rolex isn't a luxury watch company | `Rolex` | **accepted** | Pexels **Bucherer Rolex building** (night) |
| it's a tax-exempt Swiss trust | `Swiss` | **accepted** | Pexels **Lucerne Swiss heritage / Rolex street** |
| Founder Hans Wilsdorf… foundation | `Founder Hans Wilsdorf` | **all_candidates_rejected** | **MISS** (river/riverside candidates reject) |
| topic-string beat (polluted entity) | full topic as “entity” | **all_candidates_rejected** | **MISS** (fail-closed) |
| later Swiss / Rolex beats | `Swiss` / `Rolex` | **accepted** | Lucerne / Rolex building reuse |

Reject dağılımı (Phase 2.1 smoke):

| reason | count |
|--------|------:|
| `missing_required_entities` | 238 |
| `semantic_conflict` | 51 |
| `forbidden_concept` | 1 |

**Scoring kuralı (after):**

1. Forbidden / foodish → reject  
2. Concept-family conflict (finance/ownership/document/person vs nature/food) → `semantic_conflict`  
3. Entity-specific + sıfır phrase-boundary entity hit → `missing_required_entities`  
4. Entity hit var ama strong concept + zayıf topical/family → `weak_concept_evidence`  
5. Threshold / insufficient evidence → reject  
6. Accept yalnızca entity + topical/family kanıtı birlikte yeterliyse  

Entity score **tek başına** ACCEPT ettirmiyor.

---

## Entity extraction before / after

| Input | Phase 2 (before) | Phase 2.1 (after) |
|-------|------------------|-------------------|
| `Every billion…` | `Every` entity | **not entity** (`hygienize` + `NON_ENTITY_WORDS`) |
| `The Rolex…` | `The` risk | **dropped** |
| `Billions` | value as entity risk | **not entity** (value/quantity class) |
| `Rolex` | entity | **entity** |
| `Hans Wilsdorf` | entity | **entity** |
| `Hans Wilsdorf Foundation` | partial/noise | **multi-word phrase kept** |
| `Geneva` / `Switzerland` / `Swiss` | location | **kept** |

Heuristic: `extract_proper_phrases` → `hygienize_entities`.  
LLM storyboard entities de aynı `hygienize` filtresinden geçiyor.

Smoke entity seti: `Founder Hans Wilsdorf`, `Rolex`, `Swiss`, *(bir beat’te topic string — residual planner pollution; gate fail-closed MISS)*.  
`Every` / `The` / `Billions` **yok**.

---

## River regression (A)

**Unit:** `test_river_every_billion_must_reject` — MUST REJECT  
Spoken/intent: *Every billion…* + document/finance need  
Candidate tags: `every flower, stream, river, rocks, nature`  
→ reject (`semantic_conflict` veya entity hygiene sonrası evidence yok)

**Smoke:** Hans / foundation beat’lerinde riverside / river metadata **selected değil**; reject path’te görüldü (`missing_required_entities` / conflict). Final selected’da river/nature/food **yok**.

---

## Bakery regression (B)

**Unit:** `test_bakery_foundation_still_rejects` — `forbidden_concept`  
Foundation/Rolex context + bakery/cookie/pastry → REJECT  

Smoke selected metadata’da bakery/food hit **yok**.  
*(Not: splitscreen alt panel “satisfying” B-roll yemek gösterebilir — bu Director gate seçimi değil; `fetch_satisfying_clip`.)*

---

## False entity + token boundary (C, D)

| Test | Sonuç |
|------|--------|
| C `Every` not extracted | pass |
| D `entity_phrase_in_blob("Every", "…every flower…")` → False | pass |
| D `Hans` ⊄ `handsome` | pass |
| D multi-word `Hans Wilsdorf` phrase match | pass |

---

## Positive controls (E)

| Case | Unit | Smoke |
|------|------|-------|
| Hans Wilsdorf + archive metadata → ACCEPT | pass | Stock’ta portrait yok → **MISS** (doğru fail-closed; AI_MAX=0) |
| Rolex + Rolex/watch metadata → ACCEPT | pass | **Rolex building ACCEPT** |
| Geneva/Switzerland location → ACCEPT | pass | **Swiss/Lucerne heritage ACCEPT** |

---

## Caption başlangıcı

| | Phase 2 | Phase 2.1 |
|--|---------|-----------|
| Hook plan `karaoke_start_seconds` | 1.8 (= hook end) | planner ≤0.5; smoke **0.0** |
| Pipeline ASS | delay / blank risk | **force `karaoke_start_seconds=0.0`** |
| Layout | suppression risk | Hook = Hook style (üst); karaoke = Default (alt) — aynı anda, ilk ~1.8s captionsız bırakılmıyor |

**Frame kanıtı (`phase21_frames/main_0_3.jpg`):** t≈0.3s — hook *“The Rolex Foundation Secret:”* + karaoke *“ROLEX ISN'T”* (Rolex sarı highlight).

---

## Test sonuçları

```
Director / Phase2 / Phase2.1 / gate regression:
34 passed in 0.59s

Full suite (DIRECTOR_ENABLED=false):
259 passed, 2 failed
```

**External (bu phase’de düzeltilmedi):**

- `tests/test_ai_visuals.py::test_generate_ai_image_success`
- `tests/test_ai_visuals.py::test_generate_ai_image_fallback_on_error`  
→ Fal HTTP 403 / auth-billing sınıfı (önceki smoke’larda da aynı; `DIRECTOR_AI_IMAGE_MAX=0` ile bypass).

---

## Gerçek smoke — asset seçimleri

**Job:** `20260923-050839` · **engine:** `director` · **clips:** 5 · **reuse:** 1.4 · **AI images:** 0  

| t (plan) | spoken (kısa) | entities | gate | asset |
|----------|---------------|----------|------|-------|
| 0.0–2.4 | Rolex isn't a luxury watch company | Rolex | accepted | Pexels Rolex/Bucherer building night |
| 2.4–4.0 | tax-exempt Swiss trust | Swiss | accepted | Pexels Lucerne Swiss heritage / Rolex street |
| 4.0–5.6 | Founder Hans Wilsdorf… | Founder Hans Wilsdorf | **MISS** | — |
| 5.6–7.2 | (topic-polluted entity beat) | topic string | **MISS** | — |
| 7.2–8.8 | Swiss… | Swiss | accepted | Lucerne Swiss |
| 10.4–12.0 | Rolex… | Rolex | accepted | Rolex building |
| 12.0–13.6 | Swiss… | Swiss | accepted | Lucerne Swiss |

### İlk ~8s görsel doğrulama (main mp4 frames)

| t | Görünen |
|---|---------|
| 0.3s | Rolex building + hook + karaoke **ROLEX ISN'T** |
| 1.5–2.8s | Swiss street / Rolex+Bucherer + Swiss flags; karaoke *WATCH COMPANY* / *TAX-EXEMPT SWISS* |
| 4.2s | Rolex building (reuse after miss beats — render kısa) |

**River/nature/food Director selected:** yok.

### Operasyonel notlar (Phase 2.1 dışı / residual)

1. **Main video süresi 5.1s** vs TTS/audio ~25.9s / splitscreen 25.9s — `render_video` `-shortest` + kısa still-derived stock clip’ler; render_done `audio_duration=25.87` raporluyor ama mux video kısa kesiyor. Gate doğruluğunu bozmuyor; timeline uzunluğu ayrı bug (Phase 3 değil).  
2. **LLM entity pollution:** bir beat’te tüm topic string “entity” olarak geldi → fail-closed MISS (tercih edilen davranış). İleride planner’da topic-as-entity scrub eklenebilir.  
3. **Hans Wilsdorf portrait** stock’ta yok + AI kapalı → MISS (yanlış river yerine boş tercih).  
4. Host `DIRECTOR_ENABLED` / SQLite `jobs.db` awaiting_approval; smoke öncesi `clear_pending_mirror` şart.  
5. Splitscreen **alt** panel satisfying B-roll (yemek vb.) Director seçimi değil.

---

## Kod yüzeyi (mimari korundu)

- `director_gate.py` — `hygienize_entities`, `entity_phrase_in_blob`, `CONCEPT_FAMILY_LEXICON` / conflict pairs, evaluate_asset semantic layer  
- `stock_media.py` — proper-phrase extract → hygienize  
- `director_planner.py` — entity lists hygienize; karaoke cap ≤0.5  
- `pipeline.py` — ASS karaoke forced `0.0` (hook üst / karaoke alt)  
- `tests/test_director_phase21.py` — regressions A–E  

Phase 1 gate + Phase 2 beat director mimarisi korundu; büyük refactor yok.

---

## Durum

**Phase 2.1 tamam.** Smoke + rapor hazır. **Phase 3’e geçilmedi.** Onay bekleniyor.
