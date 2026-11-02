# Documentary Engine V2 — Stage D Report

**Status:** COMPLETE — Shot Director planning/selection. No Stage E+.  
**Date:** 2026-09-24  
**DOCUMENTARY_ENGINE_V2:** OFF  
**Wired into `/generate`:** NO  
**Render / Publish:** NO  

**Remote VLM:** `REMOTE_VLM_NOT_VALIDATED` — API keys present; configured model `groq/qwen/qwen3.8-27b` returned `VLM_INVALID_RESPONSE` (not usable structured multimodal). Fail-closed to UNCERTAIN (never metadata ACCEPT). Stage D is **code-complete**, **not production-ready** for live VLM until a vision-capable model is validated.

---

## Architecture

```
VerifiedStory + StoryBeat
  → DocumentaryShotDirector → ShotRequirement(s)
  → compile_search_intents → SearchIntent families
  → Stage B acquire_candidates (live) OR fixtures (offline)
  → cheap_prefilter
  → Stage C verify_candidate (budgeted)
  → ShotCandidateRanker (hard constraints → soft scores)
  → ShotSelection + VisualInformationUnit
  → BeatCoverageReport
  → BeatRecoveryEngine (failure-aware; no generic filler)
  → DocumentaryDirectorPlan
```

Package: `video-worker/app/documentary_v2/director/`

| Module | Role |
|--------|------|
| `shot_director.py` | Beat → explicit ShotRequirement |
| `query_compiler.py` | Multi-family SearchIntents |
| `ranker.py` | Hard constraints + explainable soft weights |
| `viu.py` | Semantic VIU keys (not crop/zoom) |
| `coverage.py` | COVERED / PARTIAL / UNCOVERED |
| `recovery.py` | Failure taxonomy + recovery ladder / placeholders |
| `pipeline.py` | `run_director_plan` orchestrator |

---

## Shot Director

Maps narrative role / domain → `visual_purpose`, `evidence_role`, `motion_requirement`, `strict_entity_mode`, media types, forbidden decorative concepts (generic — not Rolex-specific).

Purposes: IDENTIFY_ENTITY, SHOW_PERSON, SHOW_PRODUCT, SHOW_PROCESS, SHOW_LOCATION, SHOW_EVIDENCE, EXPLAIN_RELATIONSHIP, ESTABLISH_CONTEXT, CREATE_PAYOFF, …

Motion: REQUIRED | PREFERRED | OPTIONAL | NOT_NEEDED (person/evidence stills OK).

---

## Query / providers

Families: ENTITY_EXACT, ENTITY_ACTION, ENTITY_CONTEXT, LOCATION, ARCHIVE, EVIDENCE, DOCUMENT, CONCEPTUAL.

Archive-first for person; document/archive for evidence; video for process. Beat-scoped pools (no global bucket).

---

## Ranking

**Hard (must pass):** verifier REJECT; strict UNCERTAIN; entity NONE; metadata conflict; contradiction; forbidden; evidence-required but decorative; motion-required but static.

**Soft (centralized weights):** entity/concept/action/location alignment, evidence value, motion suitability, genericness penalty, source novelty, confidence — breakdown stored on selection.

Wrong entity cannot win on aesthetics. Novelty breaks ties; relevance beats novelty when gap is large.

---

## VIU / reuse

VIU key = entity|concept|action|evidence|setting — **not** path/crop/zoom.  
Reuse tracked; important non-product beats with reused sources can be marked PARTIAL.

---

## Recovery

Diagnoses: NO_CANDIDATES, WRONG_ENTITY, WRONG_DOMAIN, EVIDENCE_NOT_FOUND, MOTION_NOT_FOUND, ONLY_GENERIC_CONTEXT_FOUND, VERIFIER_UNAVAILABLE, …

Actions: entity re-query, archive, motion-graphic **placeholder** (claim-linked), generated-visual **placeholder** (`synthetic=true`, `evidence_prohibited=true`), alternate family/provider, REVIEW_REQUIRED.

**Never:** unrelated prior asset fill, luxury/money/skyscraper generic fallback, metadata-as-truth when verifier unavailable. Domain preserved (no ownership→manufacturing drift).

---

## Dry-run (offline fixtures, mock VLM)

Story: Rolex ownership-style multi-beat narrative (6 beats).

| Beat | Intent | Selected | Coverage | Recovery |
|------|--------|----------|----------|----------|
| product | Rolex Daytona | `c_watch` (not river) | COVERED | — |
| person | founder portrait | `c_port` archive | COVERED | — |
| ownership | evidence | none | UNCOVERED | strategy requery / evidence path |
| process | manufacturing | none (static rejected) | UNCOVERED | video/generated placeholder |
| location | Geneva | none | UNCOVERED | alternate family |
| finance | abstract | none | UNCOVERED | review (no fake evidence) |

- River selected: **NO**  
- Bakery selected: **NO**  
- Generic filler selected: **0**  
- Honest uncovered > fake 100% fill  

Artifact: `DOCUMENTARY_ENGINE_V2_STAGE_D_DRY_RUN.json`

---

## Tests

`tests/test_documentary_v2_stage_d.py` — requirement quality, intents, archive routing, river/bakery never selected, REJECT/UNCERTAIN policy, ranking hard constraints, still>irrelevant video, process static hard-fail, ownership≠market evidence, novelty/relevance, VIU identity, recovery domain/preservation, verifier-unavailable, diverse dry-run, V2 OFF / no publish.

**144 passed** (Stage A–D + render/director_phase2/beat_recovery).

---

## Completion summary

```
DOCUMENTARY ENGINE V2 — STAGE D

Tests: PASS (stage_d suite)
Full regression (A–D + key prod): 144 passed

Remote VLM validated: NO (REMOTE_VLM_NOT_VALIDATED)
Provider/model: remote_vlm / groq/qwen/qwen3.8-27b (invalid structured vision response)

Director dry run: YES (fixture/mock)
Story beats: 6
Shot requirements: 6
Candidates visually verified: 7
Accepted: 2 | Rejected: 4 | Uncertain: 1
Selected shots: 2
Unique source assets: 2 | Unique VIUs: 2
Covered: 2 | Partial: 0 | Uncovered: 4
Recovery attempts: 4
MotionGraphicPlans / GeneratedVisualPlans: as recovered (placeholders)
Generic filler selected: 0
River selected: NO
Bakery selected: NO
V2 production enabled: NO
Render: NO
Publish: NO
```

---

## Known limitations

1. Live multimodal model not validated — need vision-capable endpoint.  
2. Live Stage B acquisition in director dry-run optional (`live_acquire=True`); offline fixtures used for CI.  
3. Motion graphics / AI video not rendered (placeholders only).  
4. Not wired to production pipeline.  
5. Ownership recovery may emit motion-graphic plan when diagnose=`EVIDENCE_NOT_FOUND`.

---

## Stage E prerequisites

- Validated remote VLM (structured multimodal)  
- Consume `DocumentaryDirectorPlan` for motion-graphic render / generated media  
- EDL timing from selections + coverage  
- Still keep V2 OFF until Stage F/G acceptance  

---

## STOP

Do **not** begin Stage E render integration, FinalVideoCritic, production enablement, MİKO, or Bonsai.
