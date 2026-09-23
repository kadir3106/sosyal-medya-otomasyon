# AI Director Phase 2.2 — Entity Priority + Anti-Repetition + Hook Cleanup

**Tarih:** 2026-09-23  
**Kapsam:** Phase 2.2 only (Phase 3 yok — TTS/BGM/SFX/Telegram/AIRouter dokunulmadı)  
**Smoke job:** `20260923-061408` (offline canned script; LLM gateway 502)  
**Video:** [`video-output/director_phase22_rolex_smoke.mp4`](video-output/director_phase22_rolex_smoke.mp4)  
**Beat dump:** [`video-output/phase22_beats_summary.json`](video-output/phase22_beats_summary.json)

---

## Sonuç özeti

| Acceptance | Sonuç |
|------------|--------|
| River / bakery / unrelated B-roll | **Yok** (selected metadata clean) |
| Hans Wilsdorf → entity-specific | **MISS** (portrait yok; storefront **reject** `low_specificity` / missing entity — fail-closed) |
| Kısa aralık exact asset repeat | **Yok** (`dup_consecutive=False`; Rolex beats farklı asset id) |
| Hook static title boğmuyor | **Geçti** — max ≤1.8s + `\fad`; VO-duplicate punch skip |
| Director tests | **46 passed** (21/22 + phase2 + gate + subtitles) |
| Full suite | **265 passed / 2 Fal** (external) |
| Legacy path | Korundu |

---

## Ne değişti (minimal)

### 1–2. Entity moment + `specificity_score`
- `director_gate.compute_specificity_score` — person+portrait/archive ≫ brand storefront  
- Person beat + generic boutique/building → `low_specificity` reject  
- `selection_score = 0.40·rel + 0.45·spec + novelty − reuse_penalty`  
- Stock video/photo: first-accept yerine **batch rank → best**

### 3–4. Reuse + novelty
- `asset_fingerprint(provider, id, url)`  
- Exact recent duplicate → penalty 0.9; window içi → 0.55  
- `novelty_bonus` on concept-family delta vs recent blobs  
- Visual-change punch-in: entity shift veya exact recent → skip stretch  
- `stock_cache_reuse_ratio` artık yalnız gerçek `used_clips` hit sayar (punch-in pollution fix)

### 5. Hook cleanup (`subtitles.write_ass`)
- Cap **≤1.8s** + ASS `\fad(120,450)`  
- Hook VO ile ≥55% token overlap → **static title skip** (karaoke taşır)  
- Pipeline: `hook_max_words=5`, `hook_seconds≤1.6`

### Query ladder
- Multi-word person: `"{name} portrait archive"` first  
- Full-topic paste kaldırıldı (pollution)

---

## Before / after (Rolex moment)

| Moment | Phase 2.1 | Phase 2.2 smoke |
|--------|-----------|-----------------|
| Rolex open | Same Rolex building repeat / punch-in | Rolex building **38331117** then later **33852578** (clock) — no consecutive exact |
| Swiss | Lucerne heritage | Lucerne **37968664** (spec 0.8) |
| Hans Wilsdorf | MISS or wrong stretch | **MISS** (portrait unavailable; storefront not forced) |
| Geneva | Lake / Swiss | **Geneva flags** `19269041` (spec 0.8) |
| Hook | Long static “The Rolex Foundation Secret:” | Punch **ZERO TAX EMPIRE** ≤1.6s + fade (offline smoke) |

### Word-to-visual (`20260923-061408`)

| t | entities | gate | spec | asset |
|---|----------|------|------|-------|
| 0.0–2.4 | Rolex | accepted | 0.85 | Bucherer Rolex building 38331117 |
| 2.4–4.0 | Swiss | accepted | 0.80 | Lucerne Swiss heritage 37968664 |
| 4.0–5.6 | Hans Wilsdorf | **MISS** | 0 | — |
| 5.6–7.2 | Wall Street | **MISS** | 0 | — |
| 7.2–8.8 | (topic string) | **MISS** | 0 | — |
| 8.8–10.4 | Geneva | accepted | 0.80 | Geneva flags 19269041 |
| 10.4–12.0 | Rolex | accepted | 0.85 | Rolex wall clock 33852578 |
| 12.0–13.6 | Swiss | accepted | 0.80 | Lucerne 37968664 |

`dup_consecutive`: **False**

---

## Regression tests

| Test | Sonuç |
|------|--------|
| A/B river + bakery (Phase 2.1) | green |
| Hans portrait outranks Rolex storefront | pass |
| Reuse penalty → fresh C beats repeated A | pass |
| Entity-first portrait queries first | pass |
| Hook fade + duration cap | pass |
| Hook skip when duplicates VO | pass |

```
Director suites: 46 passed
Full: 265 passed, 2 failed (test_ai_visuals Fal 403 — external)
```

---

## Hook

- Static title no longer sits for full VO  
- Fade-out via `\fad`  
- Duplicate of opening karaoke suppressed  
- Karaoke still from t=0 (Phase 2.1 preserved)

---

## Operasyonel notlar

1. **`/generate` smoke engeli:** LLM gateway `host.docker.internal:20128` → sürekli **502 all_providers_failed** (script_gen hard-fail). Bu phase’de AIRouter değiştirilmedi.  
2. **Offline smoke:** canned Rolex script + Edge TTS + `api_key=None` heuristic Director plan → job `20260923-061408`.  
3. **Hans portrait:** stock API’de entity-specific hit yok; storefront bilerek seçilmedi (specificity). AI_MAX=0.  
4. **Main mp4 süresi kısa (~3.9s vs audio ~21s):** pre-existing `render_video` `-shortest` + still-derived clips (Phase 2.1’de de görüldü). Gate/selection doğru; mux ayrı bug.  
5. Topic-string “entity” residual → fail-closed MISS.

---

## Durum

**Phase 2.2 kod + testler + offline Rolex smoke + rapor hazır.**  
Phase 3’e geçilmedi. Full `/generate` LLM gateway ayağa kalkınca aynı hook ile tekrar üretilebilir.
