# Documentary Engine V2 — Stage D.1 Remote VLM Validation Report

**Date:** 2026-09-24  
**Scope:** Prove real multimodal VisualVerifier path for `qwen/qwen3.8-27b`.  
**Stage E:** NOT started.  
**V2 production / render / publish:** OFF.

---

## Root cause

**Primary blocker was AIRouter (gateway), not the Groq model.**

AIRouter `toInternalMessage` (`/app/server/dist/api/v1/chatCompletions.js`) only keeps `content[].type === 'text'` parts and **silently drops `image_url`**. Upstream therefore receives text-only prompts (~66–91 `prompt_tokens`). The model then invents structured JSON without pixels → Stage D `VLM_INVALID_RESPONSE` / hallucinated bakery/watch answers.

Secondary adapter gaps (fixed in D.1):

- No API-level `response_format` (`json_schema` / `json_object`)
- No `reasoning_effort=none`
- No `max_images_per_request=3` enforcement / temporal batching
- Full observation schema duplicated in the user prompt (blew Groq free-tier ITPM ~7000 on 3-image calls)

**Model kept:** `qwen/qwen3.8-27b` (vision + structured outputs confirmed on Direct Groq).

---

## Direct vs gateway matrix

| Path | Endpoint | Model ID sent | Result | Evidence |
|------|----------|---------------|--------|----------|
| **PATH 1 Direct Groq** | `https://api.groq.com/openai/v1/chat/completions` | `qwen/qwen3.8-27b` | **PASS** | Canary A: `prompt_tokens≈1846` (≥1×~2048 image budget), `contains_river=true` |
| **PATH 2 AIRouter gateway** | `LLM_API_URL` → Groq | `groq/qwen/qwen3.8-27b` | **FAIL** | Same canary: `prompt_tokens=91`, adapter raises `GATEWAY_IMAGE_DROPPED` |

Interpretation: **Direct PASS + Gateway FAIL ⇒ gateway multimodal pass-through bug** (image strip). Documentary V2 VisualVerifier now uses **Direct Groq** when `GROQ_API_KEY` is set (`VISUAL_VERIFIER_TRANSPORT=auto|direct_groq`). AIRouter remains for text LLM routing; no AIRouter redesign.

---

## Request format

OpenAI-compatible multimodal Chat Completions:

```json
{
  "model": "qwen/qwen3.8-27b",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
      ]
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {"name": "...", "strict": true|false, "schema": {...}}
  },
  "reasoning_effort": "none",
  "temperature": 0.1
}
```

- **No system prompt** on diagnostic/canary path (`use_system_prompt=False`).
- Images never sent as filesystem paths.
- Data URIs JPEG-downscaled (max side 768) before encode.
- Compact user prompt when schema is already in `response_format` (avoids ITPM blowups).

---

## Provider / model / capabilities

| Field | Value |
|-------|-------|
| Provider | Groq (Direct) |
| Model | `qwen/qwen3.8-27b` |
| `supports_images` | true |
| `supports_video_native` | false (frames-only path) |
| `supports_json_object` | true |
| `supports_json_schema` | true |
| `supports_strict_schema` | false (Groq docs: best-effort for this model) |
| `max_images_per_request` | **3** |
| `tokens_per_image_approx` | 2048 |

Code: `video-worker/app/documentary_v2/verifier/capabilities.py`

---

## Structured-output configuration

Accepted configuration recorded from live probes:

1. Prefer `response_format.type = json_schema` with full required fields + `additionalProperties: false`
2. Try `strict: true` first (canary A succeeded with `strict=True`)
3. On 400 / schema rejection → fall back to `strict: false`
4. Last resort → `json_object`
5. Provider-safe **transport schema** (`VISUAL_TRANSPORT_SCHEMA`) maps into canonical observation; domain `VisualVerification` is not weakened

Live modes observed:

- Canary A: `json_schema:strict=True`
- Full verification / temporal: often `json_schema:strict=False` after fallback

---

## Reasoning configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| `reasoning_effort` | **`none`** | Instruct / non-thinking mode for structured vision JSON |
| `reasoning_format` | **omitted** | Mutually exclusive with `include_reasoning`; avoid conflicts |
| Parser hygiene | Strip `<think>…</think>` before `json.loads` | Fail-closed if empty / invalid JSON |

---

## Image limits & batching

- Stage C may sample 5–9 frames; Groq allows **max 3 images/request**.
- Adapter plans `TemporalVerificationBatch` by deterministic interleave (e.g. 6 frames → batches `[0,2,4]` + `[1,3,5]`).
- Telemetry logged (`_batch_telemetry`); **no silent truncate**.
- Illegal >3 in a single HTTP call → `TOO_MANY_IMAGES` / UNCERTAIN (never ACCEPT).
- Inter-batch pause (`VLM_BATCH_PAUSE_SEC`, default 20s) for free-tier ITPM.
- Aggregator is conservative: presence ratios + mixed dominants; brief flash cannot become strong full-timeline ACCEPT.

---

## Real canary results (Direct Groq)

Fixtures: real Unsplash photos (`video-output/d1_fixtures/river.jpg`, `watch.jpg`).

| Probe | Result | Detail |
|-------|--------|--------|
| **A** single-image strict canary | **PASS** | `contains_river=true`, `contains_watch=false`, `prompt_tokens=1846` |
| **B** 3-frame temporal tiny schema | **PASS** | 3 images received (`prompt_tokens=5511`); `relevant_frame_indices=[0]`; `decision=REJECT` for whole-clip watch use |
| **C** river negative / Rolex metadata | **PASS** | Policy **REJECT**; `metadata_visual_conflict=true`; concept/entity NONE |
| **D** watch positive / sparse metadata | **PASS** | Policy **ACCEPT**; entity/concept **EXACT**; watch objects listed |
| **E** >3-frame batching (6 frames) | **PASS** | 2×3 batches; decision **REJECT**; `entity_presence_ratio=0.0` (not strong coverage) |

Raw sanitized probe dump: `video-output/STAGE_D1_PROBE_RESULTS.json`

---

## Latency / cost

| Call | Latency (approx) | Prompt tokens |
|------|------------------|---------------|
| A | ~1.6 s | 1846 |
| B | ~1.3 s | 5511 |
| C | ~1.4 s | 3375 |
| D | ~3.1 s | 3353 |
| E (2 batches + pause) | ~63 s wall | ~2×3-image calls |

**Average single-call latency (A–D):** ~**1.8 s**  
**Estimated cost:** Groq on-demand free/dev tier for this run; dollar cost not returned in API usage payload (treat as **~$0** for validation volume). Each image ≈ 2048 input tokens.

---

## Fail-closed behavior (preserved)

| Condition | Behavior |
|-----------|----------|
| Invalid JSON / schema | UNCERTAIN (`VLM_INVALID_RESPONSE`) |
| Timeout / HTTP error | UNCERTAIN |
| Gateway image drop | UNCERTAIN (`GATEWAY_IMAGE_DROPPED`) |
| Too many images in one HTTP call | Explicit error; never ACCEPT |
| Rate limit / ITPM 413 | `RATE_LIMITED` → UNCERTAIN |

---

## Code changes (D.1)

| File | Role |
|------|------|
| `verifier/capabilities.py` | Per-provider caps |
| `verifier/transport_schema.py` | Canary + transport JSON schemas |
| `verifier/temporal_batch.py` | Batch plan + conservative aggregate |
| `verifier/diagnostics.py` | Sanitized diagnostics (no secrets) |
| `verifier/remote_vlm.py` | Direct Groq route, structured output, drop detection, batching |
| `verifier/prompt.py` | Compact prompt; strip `<think>` |
| `config.py` | `GROQ_API_KEY`, `VISUAL_VERIFIER_TRANSPORT` |
| `tests/test_documentary_v2_stage_d1.py` | Offline regression matrix |

---

## Tests

`pytest tests/test_documentary_v2_stage_d1.py` → **15 passed, 1 skipped** (live marker).

Coverage includes: max images, batching, schema parse, invalid JSON fail-closed, reasoning strip, data URI, gateway drop detection, direct vs gateway route distinction, secrets redaction, temporal aggregate, V2 OFF, no render/publish in adapter.

---

## Remaining limitations

1. **AIRouter multimodal still broken** — do not route V2 vision through it until inbound `image_url` (+ outbound content arrays) are fixed separately.
2. **Groq free ITPM (~7000)** — 3-image + large prompt can 413; compact prompt + batch pacing required.
3. **`strict: true`** not guaranteed for this model; transport uses best-effort when needed.
4. **Native video upload** not used (frames-only by design for D.1).
5. Multi-image batches can under-report a single flash entity (E saw lake-dominant aggregates) — still fail-closed (REJECT), but presence estimation is approximate.
6. Requires **`GROQ_API_KEY`** in worker env for Direct path (not the AIRouter `air_live_*` key).

---

## Success condition

| Gate | Status |
|------|--------|
| Remote VLM validated | **YES** |
| Real pixels received | **YES** (`prompt_tokens` ≫ text-only) |
| Structured output validated | **YES** |
| Negative visual rejected | **YES** |
| Positive visual accepted | **YES** |
| Multi-frame request works | **YES** |
| Provider image limits respected | **YES** |
| Fail-closed intact | **YES** |
| V2 production enabled | **NO** |
| Render | **NO** |
| Publish | **NO** |
| Stage E | **NOT STARTED — waiting approval** |
