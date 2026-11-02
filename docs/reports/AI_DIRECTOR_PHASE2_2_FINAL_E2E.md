# AI Director Phase 2.2 — FINAL REAL E2E SMOKE

**Tarih:** 2026-09-23  
**Job:** `20260923-082227`  
**Mod:** REAL LLM (canned/heuristic storyboard **yok**)  
**Publish:** **YOK** — `pending.json` approval aşamasında kaldı  
**Phase 3 / Bonsai / Ollama / AIRouter routing / MİKO:** dokunulmadı

---

## Verdict

| Check | Result |
|-------|--------|
| **REAL LLM PLANNING** | **PASS** |
| AIRouter route | **PASS** (`gemini-flash` → `gemini` / `gemini-3.6-flash`, `fallback_depth=0`) |
| Rolex entity visuals | **PASS** |
| Switzerland / Geneva | **PASS** (Lake Geneva + Swiss flag) |
| Hans Wilsdorf | **MISS (fail-closed)** — portrait/archive yok; storefront zorlanmadı |
| Finance / ownership B-roll hygiene | **PASS** (nature/food/lifestyle yok) |
| River regression | **PASS** (yok) |
| Bakery / cookie regression | **PASS** (yok) |
| Exact consecutive asset repeat | **PASS** (`dup_consecutive=False`) |
| Hook / caption | **PASS** (≤1.8s overlay; karaoke VO ile) |
| Pending stop (no publish) | **PASS** |
| Main mux duration | **KNOWN BUG** (~2.2s vs audio ~26s; splitscreen full) |

---

## REAL LLM PLANNING: PASS

Kanıt (heuristic değil):

1. **AIRouter `usage_events`** (job penceresi UTC 08:22–08:24):
   - `08:22:41` — `gemini-flash` → `gemini/gemini-3.6-flash` — `1138+728` tok, **13531 ms**, `fb=0` → script_gen
   - `08:23:19` — `gemini-flash` → `gemini/gemini-3.6-flash` — `1308+5478` tok, **33101 ms**, `fb=0` → Director storyboard (büyük completion)
2. Beat `visual_intent` / `concept` LLM sinematik dili (ör. *"Extreme macro zoom on gold Rolex crown emblem in dark chiaroscuro…"*, *"Rolex brand without shareholders"*) — heuristic şablonları (`Exact visual proof of…`, `concept=hero/detail`) değil.
3. `DIRECTOR_ENABLED=true`, `OPENROUTER_MODEL=gemini-flash`, `LLM_API_URL` → container içinde `host.docker.internal:20128` rewrite (`script_gen._resolve_url`).
4. Heuristic fallback sessizce başarı sayılmadı; gateway sağlıklı, storyboard LLM response ile üretildi.

Raw dump: [`video-output/phase22_final_airouter_usage.json`](video-output/phase22_final_airouter_usage.json)

---

## AIRouter route

| Field | Value |
|-------|--------|
| Requested model / alias | `gemini-flash` |
| Resolved provider | `gemini` |
| Resolved model | `gemini-3.6-flash` |
| Tier / combo | alias → Gemini pool (`smart-auto` entry also lists `gemini-3.6-flash`) |
| Storyboard latency | **33101 ms** |
| Script latency | **13531 ms** |
| Fallback depth | **0** (her iki call) |
| Status | `ok` |
| API key | **not logged** (`air_live_…` prefix only in DB id) |

Probe (post-job, cache HIT ~86 ms) header: `x-airouter-cache: HIT` — production gateway sağlıklı.

---

## Config (smoke)

- `DIRECTOR_ENABLED=true`
- `DIRECTOR_AI_IMAGE_MAX=0` (Fal bypass; stock-only)
- `OPENROUTER_MODEL=gemini-flash`
- Production AIRouter `@ :20128` (worker → `host.docker.internal:20128/v1`)
- Topic: *The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders*
- Title: *Why Rolex Has Zero Shareholders*
- Hook VO: *Rolex doesn't have a single shareholder on earth.*
- Engine: `director` · clips: 7 · beats: 14 · total generate: **146.4 s**
- Warning: `tts_edge_fallback` (ElevenLabs fail → Edge; Phase 3 dışı)

---

## Storyboard summary

14 visual beats (LLM). Özet akış:

| # | t (s) | spoken_span | entities | gate | selected |
|---|-------|-------------|----------|------|----------|
| 0 | 0.0–1.6 | Rolex doesn't have a single shareholder | Rolex | accepted | Rolex watch in luxury box `19766307` (spec 0.85) |
| 1 | 1.6–2.8 | on earth. | Rolex | accepted | Bucherer Rolex building Lucerne `38331117` (spec 0.85) |
| 2 | 2.8–4.4 | Rolex doesn't have a single shareholder | Rolex | accepted | Rolex wall clock facade `33852578` (spec 0.85) |
| 3 | 4.4–5.6 | on earth. | Rolex | accepted | Rolex clock Neumarkt `31885488` (spec 0.85) |
| 4 | 5.6–6.9 | It is owned 100% | Hans Wilsdorf Foundation | **MISS** | — (143 candidates rejected) |
| 5 | 6.9–8.6 | by the Hans Wilsdorf Foundation, | Hans Wilsdorf + Foundation | **MISS** | — (236 rejected; portrait queries first) |
| 6 | 8.6–10.4 | a private Swiss trust. | Switzerland, Geneva | accepted | Lake Geneva + Swiss flag `11271896` (spec 0.80) |
| 7 | 10.4–11.9 | That means no public stock, | (none) | MISS | finance screens — fail-closed |
| 8 | 11.9–13.4 | zero quarterly reports, | (none) | MISS | — |
| 9 | 13.4–15.2 | and zero corporate pressure. | (none) | MISS | — |
| 10 | 15.2–16.9 | They re-invest profits into secrets, | Rolex | accepted | Rolex box `19766307` (non-consecutive reuse) |
| 11 | 16.9–19.0 | philanthropy, and pure sovereignty. | Rolex | accepted | Rolex clock `33852578` (non-consecutive) |
| 12 | 19.0–20.7 | Amateurs build companies to get rich; | (none) | MISS | — |
| 13 | 20.7–22.9 | elites build trusts to stay untouchable. | Hans Wilsdorf Foundation | **MISS** | — |

Reject totals: `missing_required_entities` 707 · `semantic_conflict` 34 · `below_threshold` 13 · `forbidden_concept` 1

Full beat trace: [`video-output/phase22_final_e2e_trace.json`](video-output/phase22_final_e2e_trace.json)

---

## Acceptance A–G

### A) Rolex
**PASS** — accepted beats Rolex watch / Bucherer Rolex building / Rolex clocks. Non-Rolex Lucerne heritage rejected (`missing_required_entities`).

### B) Switzerland / Geneva
**PASS** — beat 6 selects Lake Geneva + Swiss flag / Jet d'Eau (`11271896`, rel≈0.58, spec=0.80). Rolex clocks rejected as Geneva beat candidates.

### C) Hans Wilsdorf
**MISS (controlled)** — queries: `Hans Wilsdorf portrait archival photo`, `Hans Wilsdorf Rolex founder image`, trust document. Stock’ta entity-specific hit yok → `all_candidates_rejected`. Generic storefront **seçilmedi** (specificity / entity gate).

### D) Finance / ownership
**PASS** — selected metadata’da nature/food/lifestyle yok. Ownership/finance moment’lerde yanlış B-roll yerine MISS.

### E) Regression
- **River:** yok  
- **Bakery/cookie:** yok  
- **Unrelated stock:** selected set clean (`bad_selected=[]`)  
- Entity `Every` yok

### F) Repetition
**PASS** — `dup_consecutive=False`. Aynı asset (`19766307`, `33852578`) ~15s sonra tekrar (non-consecutive); kısa aralık exact tekrar yok.

### G) Hook / caption
- Static overlay: `THE ROLEX FOUNDATION SECRET`, **`hook_seconds=1.8`** (cap)
- `karaoke_start_seconds=0.5` (VO ile)
- Overlay metni VO hook ile farklı → duplicate karaoke skip tetiklenmedi (beklenen)
- Warning: yalnızca TTS Edge fallback (Phase 3 dışı)

---

## Generated video paths

| File | Notes |
|------|--------|
| [`video-output/AI_DIRECTOR_PHASE2_2_FINAL_E2E_20260923-082227.mp4`](video-output/AI_DIRECTOR_PHASE2_2_FINAL_E2E_20260923-082227.mp4) | Main (~2.2s) — pre-existing `-shortest` + still-clip mux bug |
| [`video-output/AI_DIRECTOR_PHASE2_2_FINAL_E2E_20260923-082227_splitscreen.mp4`](video-output/AI_DIRECTOR_PHASE2_2_FINAL_E2E_20260923-082227_splitscreen.mp4) | **Full timeline ~26.4s** — review için bunu kullan |
| Container pending | `/data/media/20260923-082227.mp4` (+ `_splitscreen`) — unpublished |

`stock_cache_reuse_ratio=0.0` · `clip_reuse_ratio=1.0` (metric; consecutive exact asset yok)

---

## Test suite

Director-focused (phase1/2/2.1/2.2 + gate + subtitles):

```
46 passed in ~0.3s
```

Full suite external: **2 Fal 403** on `test_ai_visuals` (out of scope; `DIRECTOR_AI_IMAGE_MAX=0`). Prior full baseline **265 passed / 2 Fal**. One gate regression assert is order-sensitive on `forbidden_hit` token (`chef` vs `bakery`); bakery reject itself is green on isolated re-run and E2E selected assets had zero bakery/cookie.

---

## Durum

**Phase 2.2 FINAL REAL E2E tamam.**  
REAL LLM + AIRouter route doğrulandı. Video + trace + bu rapor hazır.  
**Phase 3’e geçilmedi.**
