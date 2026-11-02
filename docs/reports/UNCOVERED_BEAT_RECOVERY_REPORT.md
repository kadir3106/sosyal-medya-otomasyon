# UNCOVERED BEAT RECOVERY FIX — Human Review Report

**Date:** 2026-09-24  
**Job ID:** `20260924-102629`  
**Canonical prior:** `20260924-074732` (ignore stale `20260924-074213`)  
**Status:** READY FOR HUMAN REVIEW — no self-accept  
**NO PUBLISH · NO Phase 4 · NO Bonsai / MİKO / AIRouter**

---

## Compact summary

| Field | Value |
|--------|--------|
| **Duration** | ~24.8s |
| **Story beats** | 8 |
| **Important beats** | 8 tracked |
| **Covered** | **7** |
| **Partial** | 0 |
| **Uncovered** | **1** (beat 7 — recovery attempt cap reached) |
| **Unique source assets** | **3** (was 2) |
| **Unique visual information units** | 4 |
| **Beat-by-beat coverage** | see below |
| **Recovery attempts** | 4 important beats recovered via evidence motion graphic (+ wiki person archive on others) |
| **Providers tried** | wikipedia_pageimage, motion_graphic (stock Pexels heavily rate-limited / 429) |
| **Motion graphics used** | Yes — ownership hierarchy diagrams (evidence-bound) |
| **Evidence visuals used** | Yes |
| **StoryConsistencyGate** | **PASS** |
| **NoSlideshowQualityGate** | **FAIL** — `IMPORTANT_BEAT_UNCOVERED` (1 remaining; diagnostics include attempts/why) |
| **FactQualityGate** | verify + domain-locked replacements; ownership narrative retained |
| **Output** | `video-output/UNCOVERED_BEAT_RECOVERY_E2E_20260924-102629.mp4` |
| **Trace** | `video-output/UNCOVERED_BEAT_RECOVERY_TRACE_20260924-102629.json` |
| **Report** | `UNCOVERED_BEAT_RECOVERY_REPORT.md` |

---

## What changed (recovery only)

- `BeatCoverage` + failure taxonomy (`NO_CANDIDATES`, `PROVIDER_FAILURE`, …)
- Generic query-family generation (ENTITY / STRUCTURE / EVIDENCE / CONTEXT / ARCHIVE)
- Recovery ladder with capped stock attempts; **ownership → evidence motion graphic** when verified facts exist
- Shared-asset rule: adjacent same-subject OK; unrelated reuse → UNCOVERED
- Gate diagnostics: per-beat attempts, last_failure, motion_graphic_attempted
- No silent PASS on remaining important uncovered beats

Untouched: script architecture, StoryConsistencyGate logic, AIRouter, audio, captions, render, music, publish, MİKO, Bonsai.

---

## Final script (ownership-focused)

```text
The Hans Wilsdorf Foundation is a private Swiss foundation established in Carouge.
It is the sole owner of the watchmaking group. They create artificial scarcity to
force you to bid against yourself. Do you want in the room, or just the hand holding
the key? Hans Wilsdorf (22 March 1881 – 6 July 1960) was a German watchmaker, best
known as the founder of Rolex and Tudor.
```

---

## Coverage vs prior review run

| | `20260924-074732` | `20260924-102629` |
|--|-------------------|-------------------|
| Unique sources | 2 | **3** |
| Important uncovered | 4 | **1** |
| Motion / evidence recovery | no | **yes** |
| StoryConsistency | PASS | PASS |
| NoSlideshow | FAIL | FAIL (narrower) |

Remaining uncovered beat 7: `attempts=0` (recovery capped at 4 recovered beats this run). Gate correctly does not PASS.

---

## Source map

- `wikipedia_pageimage:wiki:4bb4b8e9453e` ×3 (Hans / foundation continuity)
- `motion_graphic:mg:326c6071a18b` ×3 (ownership hierarchy)
- `motion_graphic:mg:664e916796da` ×1

---

## Tests

`tests/test_beat_recovery.py`: **18 passed** (ladder, query families, motion evidence binding, shared-asset rule, gate diagnostics, river/bakery/audio/mux/pending smokes).

---

## Verdict

Recovery ladder is live and improved coverage (4 → 1 uncovered). Ownership beats can fall back to evidence-bound motion graphics without inventing facts. One important beat still uncovered after attempt budget — gate remains FAIL with explicit diagnostics.

**STOP.** Awaiting human review.
