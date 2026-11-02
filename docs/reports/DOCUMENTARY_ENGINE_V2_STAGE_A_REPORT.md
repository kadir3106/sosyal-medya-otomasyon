# Documentary Engine V2 — Stage A Report

**Status:** COMPLETE — infrastructure only. No Stage B+.  
**Date:** 2026-09-24  
**Flag default:** `DOCUMENTARY_ENGINE_V2=false`  
**Behavioral change:** NONE (production path unchanged)

---

## Summary

Stage A introduces canonical V2 schemas, telemetry contracts, a single top-level feature flag, pipeline-mode diagnostics, and legacy→V2 adapters. Existing stock/director render, publish, and approval flows are untouched. V2 execution is intentionally inactive (`V2_EXECUTION_ACTIVE=False`), so even if the flag is set true, mode remains `LEGACY_*`.

---

## Files changed / added

| Path | Role |
|------|------|
| `video-worker/app/documentary_v2/__init__.py` | Package exports |
| `video-worker/app/documentary_v2/schemas.py` | Canonical dataclasses + enums |
| `video-worker/app/documentary_v2/pipeline_mode.py` | Mode resolution + LEGACY_STOCK warning |
| `video-worker/app/documentary_v2/adapters.py` | Legacy dict → ProductionManifest |
| `video-worker/app/documentary_v2/telemetry.py` | Manifest write + secret redact |
| `video-worker/app/config.py` | `DOCUMENTARY_ENGINE_V2` property (default false) |
| `video-worker/app/main.py` | Startup diagnostics; `/health.pipeline` |
| `video-worker/app/pipeline.py` | Per-job `pipeline_mode` log + manifest emit |
| `docker-compose.yml` | `DOCUMENTARY_ENGINE_V2=${...:-false}` |
| `video-worker/tests/test_documentary_v2_stage_a.py` | Stage A contract tests |
| `DOCUMENTARY_ENGINE_V2_STAGE_A_REPORT.md` | This report |

**Not modified (by design):** providers, render, publishers, Remotion, VisualVerifier, AIRouter redesign, DIRECTOR_ENABLED default.

---

## Schemas introduced

All in `schemas.py` (`schema_version: "1"`):

**Story / research:** `ResearchPack`, `VerifiedClaim`, `VerifiedStory`, `StoryBeat`, `ShotRequirement`

**Media:** `MediaCandidate`, `MediaAsset`, `AssetProvenance` (license defaults to `UNKNOWN`), `VisualVerification` (Stage A = `NOT_RUN` only), `VisualInformationUnit`

**Plans / edit:** `ShotSelection`, `MotionGraphicPlan`, `GeneratedVisualPlan`, `EditDecision`, `EditDecisionList`, `RenderManifest`

**Telemetry:** `BeatTelemetry`, `ShotTelemetry`, `ModelCallTelemetry`, `QualityTelemetry`, `RenderTelemetry`, `ProductionManifest`, `QualityReport`

**Enums:** `PipelineMode`, `LicenseState`, `MediaType`, `AssetOrigin`, `GateResult`

Provenance fields: provider, source_id, source_url, download_url, preview_url, media_type, duration, dimensions, creator, license, attribution, synthetic, archive, stock, content_fingerprint, retrieved_at.

---

## Compatibility adapters

`build_production_manifest_from_legacy(...)` maps existing `word_to_visual` / script_quality / gate dicts into `ProductionManifest` without changing how those dicts are produced.

`model_call_from_airouter(...)` maps cost/latency fields into `ModelCallTelemetry` (no AIRouter redesign; secrets ignored).

Quality adapter only records gates that actually ran (`StoryConsistencyGate`, `NoSlideshowQualityGate`, `FactQualityGate`). It does **not** invent PASS for VisualCoverage / License / FinalVideo.

---

## Telemetry storage strategy

- On successful generate (still `awaiting_approval`): write  
  `{MEDIA_DIR}/DOCUMENTARY_ENGINE_V2_MANIFEST_{job_id}.json`
- Join keys: `job_id` ≡ `video_id` (Stage A); `beat_id`, `shot_id`, `asset_id`, `visual_information_id`, `claim_id`
- Timeline: `start_time` / `end_time` on beats and shots (seconds) for later retention joins
- Secret scan + redact before write (`assert_no_secrets`)
- Independent of MİKO — video-worker only

---

## Pipeline mode diagnostics

```
LEGACY_STOCK      → DOCUMENTARY_ENGINE_V2 off (or V2 path inactive) AND DIRECTOR_ENABLED=false
LEGACY_DIRECTOR   → Director on, V2 execution inactive
DOCUMENTARY_V2    → flag on AND V2_EXECUTION_ACTIVE (Stage A: never)
```

- Startup (`main` lifespan): prints mode + warns on `LEGACY_STOCK`
- Every job: `log_event(..., "pipeline_mode", ...)` + stdout line
- `/health` includes `pipeline` diagnostics block

Example warning:

```
WARNING: DOCUMENTARY_ENGINE_V2 disabled.
Current production path = LEGACY_STOCK.
This path does not use V2 VisualVerifier / EDL / FinalVideoCritic.
```

`DIRECTOR_ENABLED` compose default remains `false` (unchanged in Stage A).

---

## Feature flag behavior

| Setting | Stage A result |
|---------|----------------|
| unset / `false` | `LEGACY_STOCK` or `LEGACY_DIRECTOR`; no V2 path |
| `true` | Flag recorded in manifest; **execution still legacy** until Stage B+ sets `V2_EXECUTION_ACTIVE` |

Recorded on every `ProductionManifest`: `documentary_engine_v2`, `pipeline_mode`, `pipeline_version`, `schema_version`.

---

## Tests

`tests/test_documentary_v2_stage_a.py` covers:

- V2 flag OFF default / Stage A no DOCUMENTARY_V2 mode
- Explicit pipeline modes + LEGACY_STOCK warning
- Schema roundtrip, joinable IDs, timestamps
- UNKNOWN license, synthetic persistence
- ModelCall cost serialization (no secret fields)
- Quality reason_codes; no fake FinalVideo PASS
- Secret redact on write
- Pending/approval states unchanged (`JOB_STATES` still includes `awaiting_approval`)
- Example join chain at 8.4s

Also green (regression):  
`test_render`, `test_director_phase2`, `test_no_slideshow`, `test_script_quality`, `test_source_diversity`, `test_phase3`, `test_phase31`, `test_phase32`, Stage A suite — **all passed**.

No creative E2E. No publish.

---

## Example ProductionManifest (fake job)

Join: **video → beat @ 8.4s → shot → asset → VIU**

```json
{
  "job_id": "demo-20260924-stage-a",
  "video_id": "demo-20260924-stage-a",
  "topic": "How Rolex Daytona became a status symbol",
  "duration_sec": 42.0,
  "created_at": "2026-09-24T16:00:00Z",
  "pipeline_mode": "LEGACY_STOCK",
  "documentary_engine_v2": false,
  "pipeline_version": "legacy",
  "schema_version": "1",
  "beat_telemetry": [
    {
      "beat_id": "beat:demo-20260924-stage-a:0",
      "job_id": "demo-20260924-stage-a",
      "video_id": "demo-20260924-stage-a",
      "start_time": 8.4,
      "end_time": 12.1,
      "narrative_role": "REVEAL",
      "semantic_domain": "luxury_watch_ownership",
      "claim_ids": ["claim:daytona-paul-newman"],
      "spoken_span": "That watch was never meant for collectors."
    }
  ],
  "shot_telemetry": [
    {
      "shot_id": "shot:demo-20260924-stage-a:0",
      "beat_id": "beat:demo-20260924-stage-a:0",
      "job_id": "demo-20260924-stage-a",
      "video_id": "demo-20260924-stage-a",
      "asset_id": "asset:pexels:778899",
      "visual_information_id": "viu:demo-20260924-stage-a:0",
      "provider": "pexels",
      "media_type": "stock_video",
      "origin": "stock",
      "synthetic": false,
      "archive": false,
      "stock": true,
      "license": "STOCK_LICENSED",
      "start_time": 8.4,
      "end_time": 12.1,
      "verification_status": "NOT_RUN"
    }
  ],
  "assets": [
    {
      "asset_id": "asset:pexels:778899",
      "origin": "stock",
      "visual_information_id": "viu:demo-20260924-stage-a:0",
      "provenance": {
        "provider": "pexels",
        "source_id": "778899",
        "source_url": "https://www.pexels.com/video/778899/",
        "license": "STOCK_LICENSED",
        "synthetic": false,
        "archive": false,
        "stock": true,
        "retrieved_at": "2026-09-24T16:00:00Z"
      }
    }
  ],
  "visual_information_units": [
    {
      "visual_information_id": "viu:demo-20260924-stage-a:0",
      "asset_id": "asset:pexels:778899",
      "entity": "Rolex Daytona",
      "concept": "wrist close-up",
      "evidence_role": "product_evidence",
      "beat_id": "beat:demo-20260924-stage-a:0"
    }
  ],
  "model_calls": [
    {
      "call_id": "mc:demo-20260924-stage-a:script",
      "stage": "script",
      "provider": "airouter",
      "model": "gemini-flash",
      "latency_ms": 410.0,
      "input_tokens": 1200,
      "output_tokens": 380,
      "estimated_cost": 0.0031,
      "fallback_depth": 0,
      "status": "ok"
    }
  ],
  "quality": [
    {
      "gate": "NoSlideshowQualityGate",
      "result": "FAIL",
      "reason_codes": ["unique_sources_below_min"],
      "beat_ids": ["beat:demo-20260924-stage-a:0"],
      "shot_ids": ["shot:demo-20260924-stage-a:0"]
    }
  ]
}
```

Later analytics join example (not implemented):  
retention dip @ 8.4s → beat REVEAL → shot → pexels stock → VIU product_evidence.

---

## Migration risks

1. Manifest write failure is swallowed (logged) — must not break generate.
2. Legacy `word_to_visual` often lacks license → correctly stored as `UNKNOWN` (may look “worse” in telemetry until providers fill provenance).
3. `video_id == job_id` is Stage A convention; multi-output later must keep stable mapping.
4. Flag `true` without Stage B+ still runs legacy — diagnostics warn; operators must not assume V2 gates.

---

## Known gaps (deferred to later stages)

| Gap | Stage |
|-----|-------|
| Provider abstraction + provenance fill at fetch | B |
| VisualVerifier / VIU population | C |
| EDL + Remotion / render path change | D–E |
| FinalVideoCritic + V2 gates as PASS/FAIL | F |
| `V2_EXECUTION_ACTIVE=True` / DOCUMENTARY_V2 mode | B+ |
| MİKO analytics consumer | later (external) |
| AIRouter auto-attachment of every model call | later (adapter ready) |

---

## STOP

Stage A tests pass. **Do not start Stage B** (providers, VisualVerifier, Remotion, AI video, FinalVideoCritic) until explicit approval.
