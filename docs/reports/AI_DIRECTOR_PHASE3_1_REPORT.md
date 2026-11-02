# AI Director Phase 3.1 — Quality Polish Report

**Date:** 2026-09-23  
**Job:** `20260923-194336`  
**Scope:** Incremental quality pass (NOT Phase 4)  
**Publish:** none — pending/approval unchanged  
**Phase 2 visual freeze:** preserved (gates / retrieval hierarchy / AIRouter routing / publishers / Telegram / MİKO / Bonsai untouched)

---

## Verdict — awaiting human review

Phase 3.1 polish shipped: semantic caption chunking V2, static hook title OFF, RetentionEvent V2 (same-asset novelty), generic PERSON archive retrieval + cache.

| Check | Result |
|-------|--------|
| Regression tests (phase31 + phase3 + river) | PASS |
| Static hook overlay | OFF (`overlay_text=""`, ASS Hook style absent) |
| Hans Wilsdorf spoken → person portrait | PASS (`wikipedia_pageimage` / `wiki:4bb4b8e9453e` on beat 3) |
| Caption meaningless fragment (`ROLEX INTO A PRIVATE`) | PASS (0 malformed chunks) |
| Retention events carry semantic reasons | PASS (`named_person_introduction`, `financial_scale_claim`) |
| Same-asset transform without new download | PASS (`punch_in` / `crop_zoom`; no zoom spam) |
| River / bakery / anti-repetition | PASS (Phase 2 gates unchanged) |
| Main duration | ~25.5s (mux intact) |
| Pending unpublished | PASS |
| ElevenLabs | Edge fallback (separate issue; not tied to 3.1 visual/caption verdict) |

**Do not treat this as ACCEPT.** Human creative review required.

---

## Outputs

| Artifact | Path |
|----------|------|
| Video | [`video-output/AI_DIRECTOR_PHASE3_1_REAL_E2E_20260923-194336.mp4`](video-output/AI_DIRECTOR_PHASE3_1_REAL_E2E_20260923-194336.mp4) |
| Trace | [`video-output/AI_DIRECTOR_PHASE3_1_TRACE_20260923-194336.json`](video-output/AI_DIRECTOR_PHASE3_1_TRACE_20260923-194336.json) |
| Phase 3 baseline (compare) | [`video-output/AI_DIRECTOR_PHASE3_REAL_E2E_20260923-124217.mp4`](video-output/AI_DIRECTOR_PHASE3_REAL_E2E_20260923-124217.mp4) |

---

## Before / After (Phase 3 → 3.1)

| Metric | Phase 3 `124217` | Phase 3.1 `194336` |
|--------|------------------|--------------------|
| Total duration | ~24.63s | ~25.50s |
| Visual asset count (unique selected) | (Phase 3 run) | **4** (2 Pexels + Hans Wikipedia + Wall Street Wikipedia FP) |
| Retention event count | Phase 3 pacing only | **3** (semantic reasons) |
| Longest unchanged visual-info interval | longer holds / slideshow feel | **~2.1–2.2s** |
| Exact asset reuse | present | `19766307` ×2 (non-consecutive) |
| Person retrieval attempts | none / miss | Hans **accepted** + portrait clip |
| Person portrait success | FAIL (human review) | **PASS** (beat 3 = Hans spoken) |
| Caption chunk count | — | 12 |
| Malformed/meaningless chunks | `"ROLEX INTO A PRIVATE"` reported | **0** |
| Hook overlay duration | competing static title | **0.0s** (OFF) |
| TTS provider | edge | edge (ElevenLabs fail → fallback; separate issue) |
| Render duration | ~25s class | ~25.5s |

---

## Human-review targets (trace-backed)

### HOOK
- Static duplicate title: **absent** (`ass_has_hook_style=false`, `hook_overlay_duration=0`)
- Narration/caption starts with VO
- Strong Rolex visual on opening beats (Pexels Rolex-relevant stills)

### PERSON
Spoken: *"Founded by Hans Wilsdorf,"* (beat 3)  
- Retrieval attempted: yes  
- Candidate: Wikipedia pageimage `Hans Wilsdorf` / `wiki:4bb4b8e9453e`  
- Accepted; clip at `work/.../clip_2.mp4`  
- Shown at spoken span (not generic storefront)

**Note:** This run also accepted a Wikipedia pageimage for **"Wall Street"** (misclassified as person-like Capital Capital). Post-E2E fix: `looks_like_person_name` now rejects place tokens (`street`, `avenue`, …). Next run will fail-closed on that class of entity.

### PACING
- Retention events: `archive_reveal` (person intro) + `number_emphasis`/`punch_in` (financial claim)
- Reasons present; not random cuts
- Same-asset transforms capped / spaced (no zoom spam)

### CAPTIONS
- Exact transcript preserved (grouping only)
- Proper nouns / money units kept together
- No orphan preposition fragments in harvest

---

## What changed (code)

| File | Change |
|------|--------|
| `app/phase3_retention.py` | **NEW** RetentionEvent V2 + long-hold / same-asset plan |
| `app/person_archive.py` | **NEW** Wikipedia person portrait + validated cache |
| `app/subtitles.py` | Caption semantic chunking V2; marketing title suppress |
| `app/director.py` | Retention pre-pass; person archive before stock; Wikimedia UA download |
| `app/director_planner.py` | Hook default empty; generic person heuristic (no Hans hardcode) |
| `app/pipeline.py` | `PHASE3_HOOK_TITLE_ENABLED` default OFF |
| `app/config.py` | `PHASE3_HOOK_TITLE_ENABLED` |
| `tests/test_phase31.py` | Regression suite (1–16 + person/place guards) |

---

## Separate issues (not Phase 3.1 blockers)

1. **TTS:** ElevenLabs → Edge fallback again (`tts_edge_fallback` / voice id env). Do not fold into creative accept/reject.
2. **Wall Street false person** on this E2E — detector tightened after harvest; confirmed Hans path works.
3. Some beats still miss gated stock (foundation/document) — Phase 2 fail-closed; not reopened here.

---

## STOP

Video + trace + report ready.  
**No Phase 4. No ACCEPT. Awaiting human evaluation.**
