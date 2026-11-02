# Script Quality & Fact Verification — Factcheck Report

**Date:** 2026-09-24  
**Job ID:** `20260923-220853`  
**Status:** READY FOR HUMAN REVIEW (NO PUBLISH)  
**Frozen:** Phase 2 visual + Phase 3/3.1/3.2 audio-retention-caption (untouched)

---

## Artifacts

| Artifact | Path |
|----------|------|
| Video | `video-output/SCRIPT_QUALITY_REAL_E2E_20260923-220853.mp4` |
| Split-screen | `video-output/SCRIPT_QUALITY_REAL_E2E_20260923-220853_splitscreen.mp4` |
| Trace | `video-output/SCRIPT_QUALITY_TRACE_20260923-220853.json` |
| Baseline | `SCRIPT_QUALITY_BASELINE.md` |
| Response dump | `video-output/script_quality_e2e_resp.json` |

---

## Pipeline (new)

```text
topic
  → AIRouter script generation (existing script_gen)
  → claim extraction (script_claims)
  → FactVerificationProvider (Wikipedia evidence — not LLM memory)
  → claim decisions (keep / soften / remove; HIGH unknown = fail-closed)
  → batch quality editor (1 LLM call when gateway OK; local repair fallback)
  → residual absolute strip
  → TTS(final_script) → existing Director + Phase 3.2 → pending
```

Integration: `pipeline._generate_video_sync` after `generate_script`, before TTS.

---

## Rolex topic

> The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders

### Raw script (AIRouter)

```text
Zero shareholders. Rolex doesn’t exist on any stock exchange. A hundred percent Swiss trust secret no investor sees. Founded by Hans Wilsdorf, the Hans Wilsdorf Foundation owns it all. No IPO. No liquidity. No public access. Amateurs chase profits; elites build unassailable moats. Is privacy power or isolation?
```

### Final script (after verification + quality)

```text
Founded by Hans Wilsdorf, the Hans Wilsdorf Foundation owns it all. No IPO. No liquidity. Is privacy power or isolation?
```

Estimated spoken duration: **~7.7 s** (20 words @ ~155 wpm). Short vs prior Hormozi drafts — aggressive fail-closed removal of unverified HIGH/MEDIUM claims.

---

## Extracted claims & decisions

| Claim | Type | Risk | Verify? | Evidence status | Decision |
|-------|------|------|---------|-----------------|----------|
| Zero shareholders. | ownership | HIGH | yes | unknown | **remove** (fail-closed) |
| Rolex doesn’t exist on any stock exchange. | corporate | MEDIUM | yes | unknown | soften (text unchanged; later dropped by repair) |
| A hundred percent Swiss trust secret no investor sees. | ownership | MEDIUM | yes | unknown | soften → dropped (incomplete / absolute) |
| Founded by Hans Wilsdorf, the Hans Wilsdorf Foundation owns it all. | ownership | HIGH | yes | **supported** | **keep** |
| No IPO. | corporate | MEDIUM | yes | unknown | soften keep-as-is |
| No liquidity. | rhetorical | LOW | no | skip | keep |
| No public access. | rhetorical | LOW | no | skip | keep → dropped in final polish |
| Amateurs chase profits; | rhetorical | LOW | no | skip | keep → dropped (incomplete clause) |
| elites build unassailable moats. | rhetorical | LOW | no | skip | keep → dropped |
| Is privacy power or isolation? | rhetorical | LOW | no | skip | keep |

### Rolex-sensitive themes (evidence-driven, not pre-judged)

| Theme | Outcome |
|-------|---------|
| Ownership / Hans Wilsdorf Foundation | Wikipedia intro supports foundation ownership of Rolex → claim kept (wording still strong: “owns it all”) |
| Zero / no shareholders absolutes | HIGH + unknown/partial → removed or forced toward “public” framing |
| Tax-free / billions / entire market | Not present in this raw draft; residual strip still blocks them if editor invents them |
| 100% / hundred percent | Softened/stripped when not evidenced as exact % |
| Secret / no investor sees | Removed (unsupported sensational framing) |

Evidence provider: **Wikipedia** (en.wikipedia.org API extracts). Priority intended by design: official > institutional > journalism; current implementation uses Wikipedia as the accessible reputable reference layer (not SEO blogs, not AIRouter-as-oracle).

---

## Call counts / cost

| Step | Calls (this job) |
|------|------------------|
| Script generation | 1 (AIRouter `groq/qwen/qwen3.8-27b`) |
| Wikipedia / search fetches | 5 (`search_calls`) |
| Verification reasoning LLM | 0 (heuristic score vs evidence text) |
| Quality editor LLM | **0** (fell back to local repair; see limitations) |
| Estimated extra LLM $ | ~0 beyond script gen (editor skipped) |

AIRouter route: `OPENROUTER_MODEL=groq/qwen/qwen3.8-27b` via `LLM_API_URL` → `host.docker.internal:20128`  
(Note: `gemini-flash` returned persistent **502** during this session; model env pointed at working Groq id — **routing code unchanged**.)

TTS: Edge fallback (`tts: edge`). Engine: Director.

---

## Tests

| Suite | Result |
|-------|--------|
| `tests/test_script_quality.py` (reqs 1–17 coverage) | **18 passed** |
| `tests/test_director_phase2.py` | PASS (with phase3/31) |
| `tests/test_phase3.py` | PASS |
| `tests/test_phase31.py` | PASS |
| Combined Phase2/3 + script quality | **60 passed** |

Pending/approval path unchanged (`awaiting_approval` + Telegram gate; no auto-publish).

---

## Exact rewrites (examples)

| Before | After / action |
|--------|----------------|
| Zero shareholders. | **removed** (HIGH + unknown) |
| A hundred percent Swiss trust secret no investor sees. | dropped after soften/repair |
| Founded by Hans Wilsdorf, the Hans Wilsdorf Foundation owns it all. | **preserved** (supported) |
| Amateurs chase profits; | dropped (incomplete clause guard) |

Earlier iteration sample (same topic, pre-final job) also showed:

| Before | After |
|--------|-------|
| Rolex has no shareholders. | Rolex has no public shareholders. |
| Rolex channels billions tax-free… | removed / softened (tax + billions) |
| Founder Hans Wilsdorf locked 100%. | rejected (incomplete clause) |

---

## Known limitations

1. **Evidence breadth:** Wikipedia intro extracts only — not Rolex annual reports, Swiss registry filings, or journalism cross-checks.
2. **Quality editor LLM:** Often `llm_calls=0` on this gateway (JSON parse / connection); local soften + linguistic repair is the active path. When LLM does run, claim-strengthening is rejected.
3. **Residual strength:** “owns it all” / “No IPO” remain assertive; safer phrasing (“owns Rolex” / “is not publicly listed”) is the next polish target.
4. **Short finals:** Fail-closed can shrink scripts below ideal short-form length; duration estimate uses WPM, not a magic word count.
5. **Classifier edge cases:** Fragments like “No liquidity.” may still classify as rhetorical LOW; absolute lists continue to expand as we see production copy.
6. **Stock 429:** One E2E attempt failed after script-quality success due to Pexels rate limits (Director untouched); this successful job completed after cooldown.
7. **Secrets:** Trace/report contain no API keys.

---

## STOP

Human review next. Do **not** publish. Do **not** start Phase 4 / Bonsai / MİKO / AIRouter redesign / Phase 2–3 visual-audio changes.
