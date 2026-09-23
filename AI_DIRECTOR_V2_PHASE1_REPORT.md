# AI Director V2 — Phase 1 Report (Quality Gate + Regression)

**Tarih:** 2026-09-22  
**Kapsam:** Asset quality gate + regression tests only. Full storyboard **yok**.  
**Legacy:** `DIRECTOR_ENABLED=false` yolu korundu. TTS / BGM / render / Telegram / publishers / AI router routing **değiştirilmedi**.

---

## Özet

Phase 1 tamam. Eski bug (query metnini asset kanıtı sayma) kaldırıldı. Gate artık **aday metadata** üzerinden karar veriyor; bakery/cookie vb. hard-negative ile **MUST REJECT**. Onay bekleniyor — full storyboard’a geçilmedi.

---

## Değişen / eklenen dosyalar

| Dosya | Değişiklik |
|-------|------------|
| `video-worker/app/director_gate.py` | **Yeni** — `AssetCandidate`, `evaluate_asset`, `DEFAULT_FORBIDDEN_CONCEPTS`, entity eşikleri |
| `video-worker/app/director.py` | Gated retrieve; query≠asset; reject log; ungated stock fill yok |
| `video-worker/app/director_planner.py` | Heuristic: `must_show` / `avoid` / `required_entities` boş bırakılmaz |
| `video-worker/app/director_types.py` | `required_entities`; meta’ya must/avoid |
| `video-worker/app/stock_media.py` | Food denylist; `list_stock_video_candidates` + metadata; pixabay `None` vs `""` |
| `video-worker/app/pipeline.py` | `DIRECTOR_ENABLED` env’den (MagicMock config tuzağı yok) |
| `video-worker/app/config.py` | `director_enabled()` helper |
| `video-worker/tests/test_director_gate_regression.py` | **Yeni** Rolex/Wilsdorf bakery regression |
| `video-worker/tests/test_pipeline.py` | Stock cap assert (8) — `STOCK_MAX_SCENES` ile uyum |

---

## Zincir (kod gerçekliği)

```
scene (ScenePlan)
  → queries (retrieval only)
  → list_stock_video_candidates / Pexels photo list  → candidate + metadata
       (title, tags, description, url, user — provider’ın verdiği; uydurma yok)
  → evaluate_asset(candidate, SceneNeed)
       forbidden? → reject
       entity missing (entity-specific)? → reject
       relevance = f(topical∩metadata, entity∩metadata)  — query string kanıt değil
  → accept → download
  → reject → next candidate → next query → next kind → controlled AI (kota)
  → ungated stock fill: KAPALI
```

### Rolex bakery regression

Scene ihtiyacı: *Hans Wilsdorf Foundation owns every share…*  
Candidate metadata: `bakery, cookie, pastry, food…`  
→ `accepted=False`, `reason=forbidden_concept`  
Pozitif: Rolex + Geneva + watchmaking metadata → `accepted=True`  
Query-only boş metadata → `no_asset_metadata` reject  

---

## Test sonuçları

| Suite | Sonuç |
|-------|--------|
| `test_director*` + `test_director_gate_regression` + `test_stock_media` + `test_pipeline*` + `test_phase_a_quality` | **54 passed** |
| Tam `tests/` | **236 passed**, **2 failed** |

### 2 başarısız (Phase 1 ile ilgisi yok — gizlenmedi)

- `tests/test_ai_visuals.py::test_generate_ai_image_success`
- `tests/test_ai_visuals.py::test_generate_ai_image_fallback_on_error`  

Gerçek `FalAuthBillingError: HTTP 403` — ortamda `FAL_KEY` ile canlı Fal çağrısı; `ai_visuals.py` Phase 1’de dokunulmadı. Önceki mock/env etkileşimi.

---

## Davranış notları

1. **Pexels video API** çoğu zaman title/tags vermez; gate URL + user kullanır. URL’de food slug varsa reject; generic URL + entity sahne → `missing_required_entities`.
2. Heuristic LLM fail olsa bile `avoid` food taxonomy + `must_show` entity extraction taşır.
3. Alakasız stock **fallback değil**; AI yalnızca `allow_ai_generation` / kota ile.

---

## Full storyboard

**Yapılmadı.** Sonraki aşama için onay bekleniyor.
