# Documentary Engine V2 — Stage C Report

**Status:** COMPLETE — isolated VisualVerifier. No Stage D+.  
**Date:** 2026-09-24  
**DOCUMENTARY_ENGINE_V2:** OFF (default)  
**Wired into `/generate`:** NO  
**Render / Publish:** NO

---

## Architecture

```
MediaCandidate (Stage B)
  → cheap_prefilter (deterministic text; NOT visual truth)
  → VideoPreviewSampler / image preview bundle
  → frame perceptual dedup
  → VerificationCache (fp + intent + model + prompt)
  → VisualVerifierProvider.observe()  → structured observation
  → apply_decision() → ACCEPT | REJECT | UNCERTAIN
  → VisualVerification telemetry
```

**Core rule:** METADATA CAN PROPOSE. PIXELS MUST VERIFY.

Package: `video-worker/app/documentary_v2/verifier/`

| Module | Role |
|--------|------|
| `base.py` | `VisualVerifierProvider` ABC |
| `mock.py` | Offline fixture observer |
| `remote_vlm.py` | OpenAI-compatible multimodal adapter (optional) |
| `sampler.py` | Uniform + scene-change temporal sampling |
| `frame_dedup.py` | Near-duplicate frame reduction |
| `prompt.py` | Conservative prompt + JSON schema validation |
| `decision.py` | Structured policy (UNKNOWN ≠ ACCEPT) |
| `cache.py` | Intent-aware verification cache |
| `prefilter.py` | Cheap Phase-2-style prefilter |
| `service.py` | `verify_candidate` / `verify_shortlist` |
| `reason_codes.py` | Generic reason codes |

Schemas extended in `documentary_v2/schemas.py`:  
`VisualVerification` (full Stage C fields), `VisualVerificationRequest`, `PreviewFrame`, `VisualPreviewBundle`.

Config (`config.py`): `VISUAL_VERIFIER_ENABLED` (default false), `PROVIDER`, `MODEL`, `TIMEOUT`, `MAX_CANDIDATES`, `MAX_FRAMES`, `CACHE`, `FALLBACK_PROVIDER`, `PROMPT_VERSION`.

---

## VisualVerifierProvider contract

```python
observe(request: VisualVerificationRequest, bundle: VisualPreviewBundle) -> dict
```

Returns **observation only** (visible content, alignments, ratios).  
Final decision is applied by `apply_decision()` so policy stays provider-agnostic.

**Adapters:**
- `mock` — fixture tags for offline tests (default)
- `remote_vlm` — LLM_API_URL / OpenAI-compatible chat + images (no AIRouter redesign)
- Optional primary→fallback via `VISUAL_VERIFIER_FALLBACK_PROVIDER`

---

## Preview sampling

- **Image:** single frame + dimensions + content fingerprint  
- **Video:** not first/middle only — uniform timestamps + FFmpeg scene-change points, capped by `VISUAL_VERIFIER_MAX_FRAMES` (default 7)  
- Short clips 3–5; medium ~5–7; longer bounded adaptive  
- Frame aHash dedup before VLM  
- Cheap motion class from frame-hash variance: `STATIC_VIDEO` / `MINIMAL_CAMERA_MOTION` / `NATURAL_SUBJECT_MOTION` / `FAST_MONTAGE`

---

## Decision / reason codes

Decisions: `ACCEPT` | `REJECT` | `UNCERTAIN`  

Codes include: `ENTITY_*`, `CONCEPT_*`, `ACTION_*`, `LOCATION_*`, `GENERIC_BROLL`, `METADATA_VISUAL_CONFLICT`, `VISUAL_CONTRADICTION`, `MOTION_REQUIRED_BUT_STATIC`, `TEMPORAL_WEAK_COVERAGE`, `ILLUSTRATIVE_ONLY`, `EVIDENCE_VISUAL`, `PERSON_PROVENANCE_SUPPORTED`, `VLM_UNAVAILABLE`, `VLM_INVALID_RESPONSE`, …  

**No** `RIVER_BAD` / `BAKERY_BAD`.

Fail-closed: UNKNOWN alignments, VLM failure, and strict-entity uncertainty never become ACCEPT.

---

## Evidence vs illustration / authenticity / motion / genericness

Exposed on `VisualVerification`:

- `evidence_value` / `visual_role`: EVIDENCE | AUTHENTIC_CONTEXT | ILLUSTRATION | GENERIC_CONTEXT | UNRELATED  
- `authenticity_support`: AUTHENTIC_ARCHIVE | … | STOCK_ILLUSTRATION | SYNTHETIC | UNKNOWN  
- `motion_value`: STATIC_VIDEO | … | PROCESS_MOTION | FAST_MONTAGE  
- `entity_specificity`: EXACT_ENTITY | RELATED_CATEGORY | GENERIC_CATEGORY | UNRELATED  
- `genericness`: LOW | MEDIUM | HIGH  
- `entity_presence_ratio` / `concept_presence_ratio` for temporal weakness  
- `metadata_visual_conflict` + separate `metadata_supported_claims` vs `visual_supported_claims`

Ownership + generic market stock → not EVIDENCE (ILLUSTRATIVE_ONLY / REJECT when evidence required).

Person archive: trusted provenance + archival-portrait consistency → `PERSON_PROVENANCE_SUPPORTED` without face-ID hallucination.

---

## Cache

Key = SHA256(content_fingerprint + intent_signature + provider + model + prompt_version + schema).  
Same asset, different intent → different cache entry.  
`verified_at` persisted. Prompt/model/fp change → miss.

---

## Telemetry fields

On each `VisualVerification`: job/beat/shot/candidate IDs, verifier provider/model, frame count, duration, latency_ms, cache_hit, decision, confidence, reason_codes, alignments, motion/evidence/genericness, estimated_cost (when available). No secrets.

---

## Example traces

### Negative (metadata attack)

```
INTENT: Rolex watch (strict)
METADATA/query/filename: "Rolex luxury watch"
FRAMES: river, rocks, water
entity_alignment: NONE
concept_alignment: NONE
genericness: HIGH
metadata_visual_conflict: TRUE
visual_supported_claims: []
decision: REJECT
reason_codes: [ENTITY_NOT_VISIBLE, CONCEPT_MISMATCH, METADATA_VISUAL_CONFLICT, VISUAL_CONTRADICTION, GENERIC_BROLL]
```

### Positive (sparse metadata)

```
INTENT: watch product
METADATA: (empty)
FRAMES: wristwatch dial/hands
entity_alignment: STRONG
concept_alignment: EXACT
decision: ACCEPT
```

---

## Tests

**Offline unit:** `tests/test_documentary_v2_stage_c.py` — metadata attack, bakery, visual positive, temporal flash, static process motion, ownership≠evidence, person provenance, founder/office reject, VLM unavailable/invalid → UNCERTAIN, cache intent keying, frame dedup, timestamps, pending/V2 OFF.

**Live smoke:** `tests/test_documentary_v2_stage_c_live_smoke.py` (`STAGE_C_LIVE_SMOKE=true`) — optional; uses Stage B candidates + RemoteVLM when credentials exist.

**Regression:** Stage A+B+C + render/director/no_slideshow/script_quality/beat_recovery → see summary below.

---

## Required test summary

| Item | Result |
|------|--------|
| Stage C tests | **21 passed** (`test_documentary_v2_stage_c.py`) |
| Total regression suite (A+B+C + key prod) | **155 passed** |
| Visual verifier provider(s) | `mock`, `remote_vlm` |
| Live VLM used | Optional (`remote_vlm`); offline suite uses `mock` |
| Live smoke | Gated (`STAGE_C_LIVE_SMOKE=true`); not required for CI green |
| Negative visual regressions | river/bakery/office → REJECT |
| Positive visual regressions | watch (+ sparse metadata) → ACCEPT |
| Temporal test | flash coverage → TEMPORAL_WEAK_COVERAGE, not ACCEPT |
| Static-MP4 / static process | MOTION_REQUIRED_BUT_STATIC → REJECT |
| Metadata-conflict test | REJECT |
| Verifier-failure tests | UNCERTAIN (never ACCEPT) |
| V2 production enabled | **NO** |
| Render performed | **NO** |
| Publish | **NO** |

---

## Known limitations

1. Offline suite uses `MockVisualVerifier` fixture tags — live VLM quality depends on model/credentials.  
2. Scene-change sampling needs FFmpeg; without it, uniform sampling still runs when ffmpeg extract works; image path needs no ffmpeg.  
3. Motion class from frame hashes is approximate, not optical flow.  
4. Presence ratios come from VLM observation (approx), not pixel-perfect timelines.  
5. `VisualSemanticReranker` (embeddings) **not implemented** — documented optimization for later.  
6. Stage C is **not** wired into Director/pipeline production path.

---

## Stage D prerequisites

Stage D can consume:

- `VisualVerification` with reason_codes + alignments  
- Budgeted `verify_shortlist`  
- Cache + telemetry  
- Clear REJECT/UNCERTAIN fail-closed semantics  

Stage D must still implement shot selection / EDL — Stage C only verifies candidates.

---

## STOP

Stage C complete. **Do not start** Stage D Shot Director integration, motion graphics, AI video, EDL production, FinalVideoCritic, MİKO, or Bonsai until human approval.
