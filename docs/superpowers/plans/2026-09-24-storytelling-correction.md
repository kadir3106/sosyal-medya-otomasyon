# Storytelling Correction Pass — Implementation Plan

**Goal:** Story-first documentary: semantic beats → real visual information → cinematic edit. Fact layer keeps fail-closed verification but replaces unsupported story-bearing claims with evidence-backed facts (no thin collapse).

**Out of scope:** Phase 4, Bonsai, MİKO, AIRouter routing, caption/mux/BGM redesign.

## Files

| File | Responsibility |
|------|----------------|
| `app/storyboard.py` (new) | Semantic StoryBeat model, visual_information_id, coverage diagnostics |
| `app/director_planner.py` | Plan beats from final script BEFORE retrieval (DECISION→SOURCE) |
| `app/director.py` | Prefer video/archive/evidence; same-asset transform last; track visual_information_id |
| `app/phase3_retention.py` | Retention from NEW visual information, not crop spam |
| `app/script_quality.py` + `fact_verify.py` | Replacement research when HIGH claim removed; length floor |
| `app/pipeline.py` | Wire storyboard coverage into quality; review flags |
| `tests/test_storytelling_correction.py` (new) | Regressions 1–16 |

## Tasks

1. StoryBeat schema + visual_information_id helpers + coverage report
2. Planner emits required_visual_concept / evidence_role / fallback_ladder before fetch
3. Director: transform-only does not increment visual info; video-first for motion concepts
4. Retention: ban fake zoom/crop spam as diversity
5. Script: on remove HIGH → narrative purpose → Wikipedia replacement → rewrite; length floor ~22–30s
6. Tests + Rolex REAL E2E + STORYTELLING_CORRECTION_REPORT.md → STOP
