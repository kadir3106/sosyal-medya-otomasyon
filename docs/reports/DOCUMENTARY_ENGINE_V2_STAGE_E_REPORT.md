# Documentary Engine V2 — Stage E Report

**Status:** COMPLETE — Visual Recovery Generation Layer  
**Date:** 2026-09-24  
**DOCUMENTARY_ENGINE_V2:** OFF  
**Wired into `/generate`:** NO  
**Full documentary render / Publish:** NO  
**Stage F:** NOT started  

---

## Architecture

```
Uncovered beat / failure taxonomy (Stage D)
  → choose_recovery_strategy (semantic purpose)
      REAL_MEDIA | ARCHIVE_MEDIA | DOCUMENT_EVIDENCE
      MOTION_GRAPHIC | SYNTHETIC_VIDEO | ARCHIVAL_STILL | UNCOVERED
  → MotionGraphicPlan (evidence-bound)  OR  GeneratedVisualPlan (policy-gated)
  → MotionGraphicRenderer (internal PIL+FFmpeg)  OR  GeneratedVideoProvider
  → structural QA / Stage C VisualVerifier re-check
  → select only if verified; else REVIEW_REQUIRED / UNCOVERED
```

Package: `video-worker/app/documentary_v2/recovery/`

| Module | Role |
|--------|------|
| `types.py` | RecoveryStrategy, SyntheticSuitability, primitives |
| `planner.py` | Semantic strategy selection (no random B-roll) |
| `synthetic_policy.py` | SAFE / ILLUSTRATIVE / UNSAFE / REAL_MEDIA_REQUIRED |
| `budgets.py` | Attempt + cost ceilings; live gen default OFF |
| `motion_plans.py` | Evidence-bound plan builders |
| `theme.py` | DocumentaryVisualTheme (style ≠ facts) |
| `renderer.py` | MotionGraphicRenderer → vertical H.264 |
| `prompt_compiler.py` | ShotRequirement → generation prompt |
| `generation_base.py` | GeneratedVideoProvider ABC |
| `generation_mock.py` | Offline mock provider |
| `generation_fal.py` | Fal/Kling wrap of existing `ai_video_engine` |
| `remotion_bridge.py` | Optional Remotion props/CLI (not required) |
| `engine.py` | VisualRecoveryEngine orchestration + telemetry |

Stage D `BeatRecoveryEngine` can call Stage E via `execute_stage_e=True`.

---

## Recovery philosophy (enforced)

No good real media ≠ random luxury B-roll.

Strategies chosen by **visual purpose**:

| Purpose | Preferred recovery |
|---------|-------------------|
| Ownership / relationship | RelationshipGraph (verified edges) |
| Historical person | ARCHIVAL_STILL / ARCHIVE_MEDIA |
| Process | REAL_MEDIA (synthetic only if allowed + illustrative) |
| Location | MapHighlight |
| Dated milestone | Timeline (dates in claim evidence) |
| Abstract concept | SYNTHETIC_VIDEO plan (live spend gated) |
| No suitable path | UNCOVERED / REVIEW_REQUIRED |

---

## Motion graphic primitives

Implemented plan builders + renderer support:

- RelationshipGraph  
- Timeline  
- MapHighlight  
- DocumentHighlight (requires real `document_asset_id` — never fabricates docs)  
- EvidenceCard (explicit “Documentary Notes / not an official document”)  
- Counter (value must appear in VerifiedClaim text)  
- EntityFlow (renders via RelationshipGraph path)  
- Comparison / QuoteEvidence (schema-ready; EvidenceCard-style fallback)

**Visual language:** dark cinematic gradient, restrained gold accent, caption-safe zones (top/bottom/side), hierarchical reveal motion — not PowerPoint cards.

**Provenance on every render:** `provider=internal_motion_graphics`, `synthetic=true`, `evidence_role=EXPLANATORY`, claim/evidence IDs, template version, content fingerprint.

---

## Remotion integration

- Existing `remotion-pipeline/` LuxuryShort path unchanged.  
- Stage E primary renderer is **internal** (Docker-safe, no Node).  
- `remotion_bridge.py` exports props + optional `npx remotion render` hook for a future `DocumentaryPrimitive` composition.  
- Remotion is a specialized clip renderer, not the documentary engine.

---

## Evidence binding

- Relationship edges **must** include `claim_id` + `evidence_id` for supported claims.  
- Unsupported / missing claim → `MotionGraphicPlanError` (no render).  
- Timeline dates must appear in claim/evidence text (no invented years).  
- DocumentHighlight refuses empty `document_asset_id`.  
- Counter refuses values not present in the claim.

---

## Synthetic policy

| Classification | Meaning |
|----------------|---------|
| SAFE_FOR_SYNTHETIC | Abstract / illustrative context |
| ILLUSTRATIVE_ONLY | May illustrate; never evidence |
| UNSAFE_AS_SYNTHETIC_EVIDENCE | Ownership/legal/evidence beats |
| REAL_MEDIA_REQUIRED | Persons, strict entities, authentic process |

Generated plans always set `evidence_prohibited=true`.  
Synthetic video **cannot** satisfy evidence requirements.

---

## GeneratedVideoProvider

- ABC: `estimate_cost` / `generate` / `get_status` / `materialize` + capabilities.  
- Default: `mock` (`GENERATED_VIDEO_PROVIDER=mock`).  
- Adapter: `fal_kling` wraps existing `generate_kling_video_clip` — **no rebuild**.  
- `STAGE_E_LIVE_GENERATION=false` by default → Fal adapter refuses spend.

---

## Re-verification

- Generated clips: must pass injected VisualVerifier (`ACCEPT`) or are rejected (never silent select).  
- Motion graphics: structural QA (dimensions, caption band) + claim binding; explanatory selection allowed when structurally valid.  
- Real authentic footage still wins when `has_strong_real_video=True`.

---

## Cost controls

Config (`config.py`):

- `RECOVERY_MAX_ATTEMPTS_PER_BEAT` (3)  
- `RECOVERY_MAX_MOTION_GRAPHIC_RENDERS` (4)  
- `RECOVERY_MAX_AI_GENERATION_CALLS` (1)  
- `RECOVERY_MAX_GENERATION_COST_PER_VIDEO` (0.50)  
- `RECOVERY_MAX_GENERATION_COST_PER_BEAT` (0.25)  
- `STAGE_E_LIVE_GENERATION` (false)

---

## Telemetry

`RecoveryTelemetryEvent`: beat/shot, strategy, failure reason, plan IDs, provider, estimated/actual cost, latency, verification decision, selected, claim/evidence IDs, artifact path, synthetic classification.

No analytics conclusions computed (Stage E collects only).

---

## Real dry-run results

Script: `video-output/_stage_e_dry_run.py`  
Dump: `video-output/STAGE_E_DRY_RUN.json`

| Scenario | Strategy | Result |
|----------|----------|--------|
| Ownership evidence | MOTION_GRAPHIC / RelationshipGraph | Real MP4 rendered + selected |
| Founder person | ARCHIVAL_STILL | No AI person video |
| Process | REAL_MEDIA | No paid generation |
| Abstract concept | SYNTHETIC_VIDEO plan | Plan only; live gen OFF |

**Generic filler selected:** 0  

### Real motion graphic artifact

- Path: `video-output/stage_e_dry_run/jobs/stage_e_dry/recovery/motion/mg_rel_*.mp4`  
- Format: H.264, 1080×1920, ~3s, verified edges with claim/evidence IDs  
- Isolated clip only — **not** assembled into a final documentary  

### Live paid generation

**NO** (`STAGE_E_LIVE_GENERATION=false`)

---

## Tests

`pytest tests/test_documentary_v2_stage_e.py` → **20 passed**  

Also green with Stage C/D suites (71 passed in combined run).  

Covers: semantic purpose, evidence edges, timeline dates, document non-fabrication, evidence card disclaimer, counter binding, synthetic blocks, provider swappability, live gen off, cost ceiling, verifier reject path, real-media preference, ownership/founder/process/abstract scenarios, renderer file+safe areas, V2 OFF.

River / bakery regressions remain PASS (director phase tests).

---

## Known limitations

1. Internal renderer is cinematic-minimal, not a full Remotion design system yet.  
2. Comparison / QuoteEvidence use EvidenceCard-style fallback until dedicated layouts land.  
3. DocumentHighlight needs a real document bitmap asset path for premium page composition.  
4. Live Fal/Kling path exists but is off by default; requires `FAL_KEY` + flag.  
5. Stage E does not assemble EDL / final FFmpeg timeline (Stage F).  
6. AIRouter multimodal remains broken (D.1); VLM for generated re-verify should use Direct Groq when enabled.

---

## Stage F prerequisites

- EDL / timeline compiler consuming ShotSelection + recovery artifacts  
- Multi-shot documentary assembly (FFmpeg)  
- FinalVideoCritic + targeted repair  
- Optional Remotion DocumentaryPrimitive composition wired through `remotion_bridge`  
- Production enablement still gated (`DOCUMENTARY_ENGINE_V2`)

**STOP — wait for human review before Stage F.**
