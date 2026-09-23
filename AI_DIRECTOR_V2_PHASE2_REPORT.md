# AI Director V2 — Phase 2 Report

**Durum:** Visual Storyboard / Visual Beat Director uygulandı. Phase 3 (audio/pacing) **başlatılmadı**. Onay bekleniyor.

**Tarih:** 2026-09-22

---

## Özet

Director artık yalnızca “bu scene için hangi asset?” demiyor. Script’i semantik **visual beat**’lere ayırıyor; her beat entity-first retrieval + Phase 1 quality gate ile materyalleştiriliyor. Hook Director kısa punch overlay + karaoke gecikmesi ile 0–3 sn’yi koordine ediyor.

---

## Değişen dosyalar

| Dosya | Değişiklik |
|-------|------------|
| `video-worker/app/director_types.py` | `VisualBeat`, `HookDirectorPlan`, kind aliases, entity-first query helper |
| `video-worker/app/director_planner.py` | Storyboard LLM prompt; beat parse; heuristic semantic beats; hook plan |
| `video-worker/app/director.py` | Fetch **per beat**; entity-first ladder; Phase 1 gate her candidate’ta |
| `video-worker/app/subtitles.py` | `karaoke_start_seconds`, `hook_max_words`; kısa punch wrap |
| `video-worker/app/pipeline.py` | Director açıkken ASS’i Hook Director ile yeniden yazar |
| `video-worker/tests/test_director_phase2.py` | **Yeni** Phase 2 suite |
| `AI_DIRECTOR_V2_PHASE2_REPORT.md` | Bu rapor |

**Dokunulmayanlar (bilinçli):** Telegram approval, publishers, MİKO bypass, legacy `DIRECTOR_ENABLED=false` yolu, Phase 1 `director_gate`, audio/pacing (Phase 3).

---

## Yeni mimari

```
script + topic
    │
    ▼
plan_scenes() ──► AIRouter (LLM_API_URL)  ──fail──► heuristic storyboard
    │
    ▼
ScenePlanDocument
  ├── HookDirectorPlan (punch ≤6 words, karaoke delay)
  └── ScenePlan[]
        └── VisualBeat[]  (spoken_span, entities, must_show/avoid, ladder, …)
    │
    ▼
plan_and_fetch_scenes()
  for each VisualBeat:
    entity_first_queries → exact entity → entity+context → planned queries
    kind_chain (archive_photo→stock_photo, …)
    evaluate_asset()  ← Phase 1 gate (metadata, forbidden, entity threshold)
    accept | reject | controlled AI (budget)
    │
    ▼
clip_paths[] (beat sayısı) → render (mevcut schedule)
pipeline: rewrite ASS with hook plan
```

**Temel prensip:** İzleyici önemli kavramı (Rolex, Wilsdorf, Foundation, billions, Switzerland) duyduğu anda görsel olarak doğrulamalı. Generic stock, spesifik entity beat’lerinde kolay fallback değil.

---

## Visual beat JSON örneği

```json
{
  "hook": {
    "overlay_text": "Rolex owns itself",
    "hook_seconds": 1.6,
    "karaoke_start_seconds": 1.6,
    "hero_shot": "hero_closeup",
    "motion": "slow_push"
  },
  "scenes": [
    {
      "index": 0,
      "scene_type": "hook",
      "visual_intent": "Rolex crown + ownership reveal",
      "preferred_kinds": ["stock_photo", "stock_video"],
      "search_queries": ["Rolex crown logo"],
      "must_show": ["Rolex"],
      "avoid": ["bakery", "cookie", "food", "..."],
      "visual_beats": [
        {
          "spoken_span": "Rolex is not owned",
          "concept": "Rolex",
          "narrative_role": "hook",
          "primary_entities": ["Rolex"],
          "visual_intent": "Rolex product / crown hero",
          "preferred_media": ["stock_photo"],
          "must_show": ["Rolex"],
          "search_queries": ["Rolex crown watch"],
          "shot_type": "hero_closeup",
          "motion": "slow_push",
          "overlay_intent": "none",
          "fallback_ladder": ["stock_photo", "ai_image"],
          "confidence": 0.9
        },
        {
          "spoken_span": "Hans Wilsdorf built the brand",
          "concept": "founder",
          "narrative_role": "entity_proof",
          "primary_entities": ["Hans Wilsdorf"],
          "visual_intent": "Archive portrait of Hans Wilsdorf",
          "preferred_media": ["archive_photo", "stock_photo"],
          "must_show": ["Hans Wilsdorf"],
          "search_queries": ["Hans Wilsdorf portrait"],
          "shot_type": "archival",
          "confidence": 0.85
        }
      ]
    }
  ]
}
```

`archive_photo` / `document` / `chart` / `map` / `kinetic_typography` plan JSON’da kabul edilir; retrieval şu an `stock_photo` / `ai_image`’a normalize edilir (yanlış asset uydurulmaz).

---

## Test sayısı / sonuçlar

### Director suite (Phase 1 + Phase 2)

```
tests/test_director.py
tests/test_director_gate_regression.py
tests/test_director_phase2.py
→ 21 passed
```

Hook/karaoke ASS tests: `tests/test_subtitles.py` (mevcut + Phase 2 parametreleri) yeşil.

Phase 2 yeni testler (`test_director_phase2.py`):

- scene → birden fazla visual beat  
- Rolex entity-aware beat  
- Hans Wilsdorf archive/entity intent  
- billions → financial visual intent  
- Hook Director hero plan  
- hook overlay / karaoke conflict prevention  
- bakery regression hâlâ reject  
- LLM fail → güvenli heuristic fallback  
- visual beat candidate’ları Phase 1 gate’ten geçer  
- entity-first query ladder sırası  

### Full `video-worker/tests/`

```
246 passed, 2 failed
```

**2 fail (önceden var, Phase 2 ile ilgili değil):**

- `test_ai_visuals.py::test_generate_ai_image_success` — Fal Flux HTTP 403  
- `test_ai_visuals.py::test_generate_ai_image_fallback_on_error` — aynı  

---

## Fallback davranışı

| Durum | Davranış |
|-------|----------|
| LLM storyboard 400/502/parse fail | Heuristic semantic beats + full avoid/must_show |
| Entity beat, stock yok | Controlled AI yalnızca `allow_ai_generation` + budget |
| Gate reject (bakery, empty meta, missing entity) | Sonraki candidate / query / kind; **ungated stock fill yok** |
| Kind alias (archive_photo vb.) | Mevcut provider’lara map; fake asset yok |
| `DIRECTOR_ENABLED=false` | Legacy VISUAL_ENGINE yolu değişmedi |

---

## Phase 1 regression

| Kontrol | Sonuç |
|---------|--------|
| query relevance ≠ asset relevance | Korundu (`evaluate_asset` metadata) |
| forbidden / bakery | `test_bakery_*` + Phase 2 bakery beat need → reject |
| must_show / avoid | Heuristic + beat inherit |
| entity-specific threshold | Gate aynı |
| yanlış stock → reject | Ungated fill yok |
| `DIRECTOR_ENABLED` default false | Korundu |

---

## Bilinen eksikler (Phase 2 sonrası, Phase 3 değil)

1. **Gerçek archive/document/chart/map/kinetic provider’lar yok** — mimari alias hazır; retrieval hâlâ Pexels photo/video + AI image.  
2. **LLM storyboard kalitesi** AI router model/uptime’a bağlı; düşerse heuristic (iyi güvenlik ağı, daha az sinematik çeşitlilik).  
3. **Beat süresi ↔ TTS kelime hizası soft** — `duration_hint` var; Phase 3 audio/pacing ile sıkı sync planlanacak.  
4. **Stok API’de Hans Wilsdorf arşiv fotoğrafı her zaman bulunmayabilir** — gate yanlış “businessman” kabul etmez; miss → controlled AI veya boş slot.  
5. **Fal 403** testleri ortam/billing; Director Phase 2’den bağımsız.

---

## Acceptance criteria (post Phase 2 refine)

Applied without redesigning Phase 2 architecture:

| Criterion | Implementation |
|-----------|----------------|
| WORD-TO-VISUAL SYNC | `word_to_visual` chain in stats/pending: spoken_span → concept/entities → intent → queries → rejected → selected |
| MICRO-PACING | `VisualBeat.resolve_duration_hint()` — prefer 1.2–2.0s; hero/reveal soft-longer; no hard cut-every-N |
| VISUAL CHANGE ≠ NEW VIDEO | `visual_change`: punch_in / crop_zoom / archive_motion reuses prior gated asset |
| CAPTION HIERARCHY | Hook ≤6 words + karaoke_start delay (Phase 2) |
| FUTURE SFX CUES | `audio_cue` / `emphasis_cue` on beats — **audio pipeline untouched** |
| PRIORITY | `DIRECTOR_PRIORITY`: relevance > entity > storytelling > pacing > variety; no ungated fill |

---

## Onay kapısı

Phase 2 + acceptance refine tamam. **Phase 3 (audio/pacing) başlamadı.**

Onayını bekliyorum.

