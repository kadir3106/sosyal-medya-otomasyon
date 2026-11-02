# No-Slideshow Story Engine — Architecture Correction Report

**Date:** 2026-09-24  
**Job ID:** `20260924-071349`  
**Status:** READY FOR HUMAN REVIEW — **NoSlideshowQualityGate = FAIL** (transparent)  
**NO PUBLISH**

---

## A. Before / after architecture

| Before | After |
|--------|--------|
| Diversity ≈ cuts / zooms / punch-ins | Diversity ≈ `visual_information_id` (asset-bound) |
| Heuristic: same entity → auto `punch_in` | Same entity alone does **not** mint new info; `new_asset` default |
| Retention: up to 3 same-asset transforms | Cap **1** controlled same-asset transform |
| Fact-check: remove → story collapse | Remove → **replacement research** (Wikipedia evidence) → rebuild |
| Length: ceiling only | Length floor (~22s WPM) + evidence inject |
| No slideshow gate | `NoSlideshowQualityGate` → PASS / REVIEW_REQUIRED / FAIL |

**Frozen (untouched):** relevance gate, person/archive retrieval, river/bakery regressions, anti-repetition core, AIRouter routing, BGM instrumental policy, ducking/loudnorm, captions, mux, Telegram pending, publishers.

---

## B. Final verified script

**Raw (AIRouter):**
```text
Rolex generates thirteen billion dollars yearly, yet pays zero corporate tax. It has no public shareholders and zero stock on Wall Street. In 1960, founder Hans Wilsdorf placed 100% of Rolex into a private Swiss trust. True power isn't owning equity; it's hiding control inside an untouchable fortress. Is this tax genius or ultimate greed?
```
(~55 words)

**Final (after verify + replacement research + polish):**
```text
True power isn't owning equity; it's hiding control inside an untouchable fortress. Is this tax genius or ultimate greed? It has been manufactured by Rolex since 1963 in four distinct generations (or series); the second series was introduced in 1988, the third in 2000 and the fourth in 2023. While cosmetically similar, the second series introduced a self-winding movement (the first series is hand-wound), and the third series brought manufacture of the movement in-house to Rolex.
```
(~76 words, ~29.5s video)

---

## C. Replacement research

| Unsupported / removed | Purpose | Replacement (evidence) |
|----------------------|---------|------------------------|
| High-risk finance/tax/ownership absolutes softened/removed | scale / ownership / mystery | Wikipedia Rolex / Cosmograph Daytona extracts (6 facts injected) |

**Rejected claims:** 1 hard remove (+ multiple softens of HIGH/MED numbers/tax).  
**Verified replacement facts added:** 6 (Wikipedia).  

**Limitation:** replacements skewed toward **product generation history** (Daytona series) rather than **foundation ownership** — seed ranking still imperfect for ownership-first topics.

---

## D–E. Storyboard / shot list (summary)

Gate diagnostics for this job:

| Metric | Value |
|--------|------:|
| Story beats (word_to_visual) | 8 |
| Unique visual information units | 5 |
| Unique source assets | **1** |
| Real video shots (kind heuristic) | 8 |
| Archive-oriented beats | 4 |
| Document beats | 1 |
| Same-asset transform-only | 0 |
| Uncovered beats | several (gate FAIL) |
| Video duration | **29.54 s** |

Decision-first storyboard (`storyboard_before_retrieval`) runs from final script before fetch. Planner prompt now requires `required_visual_concept` + `evidence_role` and forbids zoom-as-information.

---

## F–H. Asset types / still justification / VIU

- **Primary selected asset id seen:** `38331117` (stock photo path used for manufacturing span).  
- Many beats **failed gated fetch** → uncovered (gate correctly FAIL).  
- Still usage: archive/person-oriented concepts remain allowed; transform spam capped.  
- Crop/zoom of same `asset_id` share one `visual_information_id` (tested).

---

## I. NoSlideshowQualityGate

```text
status: FAIL
reasons:
  - IMPORTANT_BEAT_UNCOVERED
```

Also `review_recommended` from coverage (`important_beats_uncovered`). Pipeline sets `quality.review_required` on FAIL/REVIEW.

This is intentional fail-closed for slideshow-shaped scarcity — **not** silently PASS.

---

## J. Tests

| Suite | Result |
|-------|--------|
| `tests/test_no_slideshow.py` | PASS |
| `tests/test_script_quality.py` | PASS |
| `tests/test_director_phase2.py` (updated same-entity policy) | PASS |
| `tests/test_phase3.py` / `phase31` / `phase32` | PASS (with earlier combined 89+) |

Covers: VIU identity under zooms, gate fake variety, archive OK path, storyboard-before-retrieval, replacement research attempt, pending/approval smoke.

---

## K–L. AIRouter / generation

- Script + director via existing AIRouter (`OPENROUTER_MODEL` / gateway).  
- Fact evidence: Wikipedia HTTP (not LLM memory).  
- Quality editor: batch call when gateway OK; else local repair.  
- No new paid AI-video provider wiring in this pass (ladder reserved; stock/archive first).

---

## M. Known limitations

1. **Gate FAIL** — too few unique source assets for multi-beat story; retrieval/gate still scarce for Rolex-specific video.  
2. **Replacement topic drift** — ownership story filled with Daytona manufacturing facts.  
3. **Rhetorical openers** still allowed (“True power isn’t owning equity…”) — fact layer focuses on HIGH claims.  
4. **ArchiveVideoProvider / MotionGraphicPlan** — interfaces/diagnostics only partially; full archive-video + motion-graphics engines not fully built.  
5. **Duplicate beats** in word_to_visual log (scene expansion) inflate uncovered lists.

---

## Artifacts

| File | Path |
|------|------|
| Video | `video-output/NO_SLIDESHOW_REAL_E2E_20260924-071349.mp4` |
| Split | `video-output/NO_SLIDESHOW_REAL_E2E_20260924-071349_splitscreen.mp4` |
| Trace | `video-output/NO_SLIDESHOW_TRACE_20260924-071349.json` |
| Script quality trace | `/data/media/SCRIPT_QUALITY_TRACE_20260924-071349.json` (container) |
| Report | `NO_SLIDESHOW_STORY_ENGINE_REPORT.md` |

---

## Human review package (compact)

```text
Duration:                 ~29.5s
Story beats:              8
Total shots (entries):    8

Real video shots:         8 (kind heuristic; many uncovered = no durable asset)
Archive video shots:      0
Stock video shots:        (mixed / gated)
Motion graphic shots:     0
AI video shots:           0
Archive still shots:      0
Other still shots:        (1 unique source asset observed)

Unique visual information units: 5
Same-still transform-only events: 0

Unsupported claims removed: 1 (+ softens)
Verified replacement facts added: 6

NoSlideshowQualityGate:   FAIL (IMPORTANT_BEAT_UNCOVERED)
FactQualityGate:          research_attempted=true; fail-closed HIGH unknown

Total LLM calls:          (script gen + optional editor; see worker logs)
AIRouter route:           unchanged architecture (env model)
Generation cost:          Wikipedia free + existing stock path

Output video: video-output/NO_SLIDESHOW_REAL_E2E_20260924-071349.mp4
Trace:        video-output/NO_SLIDESHOW_TRACE_20260924-071349.json
Report:       NO_SLIDESHOW_STORY_ENGINE_REPORT.md
```

---

## STOP

Human review next.  
**Not** published. **Not** Phase 4 / Bonsai / MİKO / AIRouter redesign.
