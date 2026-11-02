# SOURCE DIVERSITY + STORY DRIFT FIX — Human Review Report

**Date:** 2026-09-24  
**Job ID:** `20260924-074732`  
**Status:** READY FOR HUMAN REVIEW — gates below (no self-accept)  
**NO PUBLISH · NO Phase 4 · NO Bonsai / MİKO / AIRouter redesign**

---

## Compact summary

| Field | Value |
|--------|--------|
| **Duration** | ~28.0s |
| **Story beats** | 8 |
| **Shots** | 8 |
| **Unique source assets** | **2** (was 1 on prior FAIL) |
| **Unique visual information units** | 5 |
| **Source reuse map** | `wikipedia_pageimage:wiki:4bb4b8e9453e` ×3 · `pexels_photo:38331117` ×1 |
| **Important uncovered beats** | 4 (hook “Ever.”, evidence “crown reigns…”, biography fragment, trailing “Ever.”) |
| **Replacement domains** | ownership (scores 0.7–1.0) — foundation / sole owner / founder biography |
| **Detected story drift** | **None** (prior run: ownership → Daytona/manufacturing) |
| **StoryConsistencyGate** | **PASS** |
| **NoSlideshowQualityGate** | **FAIL** — `IMPORTANT_BEAT_UNCOVERED` |
| **FactQualityGate** | Script verify + replacement research ran; unsupported ownership absolutes removed; domain-locked replacements injected |
| **Output** | `video-output/SOURCE_DIVERSITY_E2E_20260924-074732.mp4` |
| **Trace** | `video-output/SOURCE_DIVERSITY_TRACE_20260924-074732.json` |
| **Report** | `SOURCE_DIVERSITY_STORY_DRIFT_FIX_REPORT.md` |

---

## What was fixed

1. **ReplacementIntent + semantic domain lock** — ownership/governance/founder replacements reject manufacturing/product (Daytona, Cosmograph, self-winding series text).
2. **StoryConsistencyGate** — FAIL on domain drift; strip + re-inject domain-safe facts before TTS.
3. **Unique source asset model** — `source_asset_key` / `analyze_source_assets` separate `shot_count` vs `unique_source_asset_count` (crop/trim ≠ new asset).
4. **NoSlideshowQualityGate** — flags `LOW_UNIQUE_SOURCE_ASSET_COUNT`, `EXCESSIVE_SOURCE_REUSE`, `IMPORTANT_BEAT_UNCOVERED`, `SEMANTIC_DOMAIN_DRIFT`, `RETRIEVAL_COLLAPSE`.
5. **Per-beat retrieval** — important roles force `new_asset`; uncovered important beats get retry with alternate domain-preserving queries (no silent prior-asset fill).
6. **Reporting** — response/trace expose both shot and unique-source counts + reuse maps.

---

## Final verified script (ownership-focused)

```text
Ever. The crown reigns because the entity is legally immortal. The Hans Wilsdorf
Foundation is a private Swiss foundation established in Carouge. It is the sole
owner of the watchmaking group Rolex. Hans Wilsdorf was a German watchmaker, best
known as the founder of Rolex and Tudor. Hans Wilsdorf (22 March 1881 – 6 July 1960)
was a German watchmaker, best known as the founder of Rolex and Tudor.
```

No Daytona / racing / manufacturing-series drift (contrast prior E2E `20260924-071349`).

---

## Visual / coverage (transparent)

| Beat | Span (short) | Coverage | Source |
|------|----------------|----------|--------|
| 0 | Ever. | UNCOVERED | — |
| 1 | crown / legally immortal | UNCOVERED | — |
| 2 | Foundation in Carouge | COVERED | wiki portrait family |
| 3 | sole owner of Rolex | COVERED | pexels_photo:38331117 |
| 4–5 | Hans Wilsdorf founder | COVERED | wiki:4bb4b8e9453e (reuse) |
| 6–7 | date fragment / Ever. | UNCOVERED | — |

Retry log: hook/evidence/person fragments → `all_candidates_rejected` (not filled with unrelated prior stock).

---

## Tests

`tests/test_source_diversity.py` + existing no-slideshow / script-quality suites: **51 passed** (includes items 1–18 scope: unique-source identity, domain lock, coverage retry signal, novelty vs reuse scoring, river/bakery/person/music/mux/pending smoke).

---

## Verdict for human

- **Story drift fix: successful** (consistency PASS; narrative stays foundation/ownership/founder).
- **Source diversity: improved** (1 → 2 unique assets) but still thin; gate does **not** claim healthy diversity.
- **Important beat coverage: still FAIL** (4 uncovered / thin script fragments) — correctly not PASS.

**STOP.** Awaiting human review. Do not publish.
