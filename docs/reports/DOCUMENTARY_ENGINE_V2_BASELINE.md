# Documentary Engine V2 — Baseline (Code as Source of Truth)

**Date:** 2026-09-24  
**Scope:** Pre-implementation inspection only. **No V2 code changes in this document.**  
**Repo:** `C:\Projects\sosyal-medya-otomasyon`

---

## 1. CURRENT architecture (summary)

The product is a **Python `video-worker`** (FastAPI + FFmpeg) that generates short vertical videos, stops at **human approval** (SQLite + `pending.json` + Telegram), then publishes via platform adapters.

There are **two visual product modes** and **one experimental side path**:

| Mode | Activation | Visual language |
|------|------------|-----------------|
| **Legacy stock** | `DIRECTOR_ENABLED=false` (compose **default**) + `VISUAL_ENGINE=stock` | Scene schedule from audio duration → stock clips → Ken Burns on stills / zoompan on video → FFmpeg xfade |
| **Director / “no-slideshow” stack** | `DIRECTOR_ENABLED=true` (env override; used in recent E2Es) | LLM/heuristic beats → gated stock/person/AI → retention transforms → recovery/motion graphics → NoSlideshow gate |
| **Remotion** | `POST /render-remotion` or Telegram NL “video yap” | Host-only React Remotion; **not** Docker daily `/generate` |

Recent Phase 2–3.2 / no-slideshow / source-diversity / beat-recovery work **layered onto Director**, not onto a clean documentary EDL architecture. The result is a **hybrid**: better gates and traces, but still **search → metadata gate → accept**, with Ken Burns / punch-in / same-asset transforms as primary “motion.”

There is **no** multimodal visual inspection of frames, **no** VisualVerifier, **no** EditDecisionList-driven render, **no** FinalVideoCritic on the MP4.

---

## 2. CURRENT production path (real)

```
POST /generate  (video-worker/app/main.py::generate)
  → 409 if pending / has_blocking_job
  → jobs.create_job(state=generating)
  → pipeline.generate_video → asyncio.to_thread(_generate_video_sync)

_generate_video_sync (video-worker/app/pipeline.py):
  1. Topic (request or topics.select_next_topic)
  2. script_gen.generate_script          [LLM via LLM_API_URL / OpenRouter]
  3. script_quality.refine_script        [claims → Wikipedia verify → replace research → LLM edit]
  4. phase3_profiles (narration/music/pacing)
  5. tts.synthesize_speech               [ElevenLabs → Edge fallback]
  6. subtitles.write_ass (first pass)
  7. audio_bgm.get_or_create_bgm
  8. Visuals:
       if DIRECTOR_ENABLED:
         director.plan_and_fetch_scenes
       elif VISUAL_ENGINE != stock + prompts:
         ai_video_engine.generate_video_scenes
       else:
         stock_media.fetch_stock_clips
  9. optional sfx.build_sfx_track
 10. render.render_video                 [FFmpeg xfade + ASS + BGM duck/loudnorm]
 11. optional sibling *_splitscreen.mp4
 12. jobs.update_job(awaiting_approval) + write_pending_mirror
 13. Telegram notify (approve/reject)
 14. finally: delete work_dir

Approve (Telegram /publish):
  → main._run_publish → YouTube / TikTok / IG / FB (+ optional Threads/X/Pinterest)
  → clear pending / mark done
```

**Orchestration:** n8n `workflow_a_daily_video_pipeline.json` hits `/generate` on schedule, then Telegram sendVideo (may duplicate worker notify).

**Code truth vs recent reports:** Compose defaults `DIRECTOR_ENABLED=false`. Human E2Es that set `DIRECTOR_ENABLED=true` exercise the Director stack; default Compose deploy may still be **legacy stock**.

---

## 3. Working components (keep)

| Area | Location | Notes |
|------|----------|--------|
| Claim extraction | `script_claims.py` | Risk/type classification |
| Fact verification | `fact_verify.py` | Wikipedia evidence; fail-closed HIGH unknown |
| Replacement research + domain lock | `script_quality.py` + `story_domains.py` | Prevents ownership→manufacturing drift (StoryConsistencyGate) |
| TTS | `tts.py` | ElevenLabs + Edge; Phase3 voice settings |
| Captions | `subtitles.py` | Word-boundary ASS karaoke |
| Music rules | `audio_bgm.py` + `phase3_profiles.py` | Instrumental preference; silence > wrong music |
| Loudness / ducking | `render.py` + Phase3 flags | Preserved |
| Mux duration | `render.py` | Known fix retained |
| Person archive | `person_archive.py` | Wikipedia portrait cache (Director path) |
| Relevance prefilter | `director_gate.py` | Entity/concept contradiction gates (metadata-only) |
| Source asset identity | `story_domains.source_asset_key` | Crop/trim ≠ new asset (reporting) |
| Visual information id (asset-bound) | `storyboard.compute_visual_information_id` | Zoom ≠ new VIU (partial) |
| Beat recovery + motion graphic | `beat_recovery.py` | Ladder + PIL hierarchy diagram |
| NoSlideshow / coverage gates | `no_slideshow_gate.py` | Soft/hard FAIL with diagnostics |
| Pending / approval | `jobs.py` + `telegram_bot.py` | SQLite + pending.json; no auto-publish |
| Publishers | `publishers/*` | Interfaces stable |
| AIRouter / LLM waterfall | `script_gen` / OpenRouter URL | **Do not redesign routing** |

---

## 4. Obsolete / experimental / side paths

| Item | Classification |
|------|----------------|
| `remotion-pipeline/` + `remotion_runner.py` + `POST /render-remotion` | Experimental host Remotion; not Docker daily path |
| Telegram NL → Remotion | Diverges from `/generate` FFmpeg path |
| `VISUAL_ENGINE=flux_kenburns\|hybrid\|kling\|ai` | Legacy AI-first; compose default is `stock` |
| `apply-quality-upgrade-local.ps1` / hybrid-flux patches | Local experiment scripts |
| `publishers/tiktok_browser.py` | Manual helper; not in `_run_publish` |
| Reserved Director kinds (`chart`, `map`, `ai_video`, …) | Aliased to `stock_photo` / `ai_image`; no real providers |
| Root `*_REPORT.md` phase docs | Human-review artifacts; not runtime |

---

## 5. Technical debt (structural)

1. **Flag split-brain:** `DIRECTOR_ENABLED` read from `os.environ` in pipeline, not only `config`; Phase3 flags in `config.py` defaults but **not** in `docker-compose.yml`.
2. **Layered patches:** Phase 2 → 2.1 → 2.2 → 3.x → script quality → no-slideshow → source diversity → beat recovery — overlapping responsibilities (`storyboard` / `story_domains` / `beat_recovery` / `phase3_retention` / `no_slideshow_gate`).
3. **Dict-heavy contracts:** `word_to_visual`, quality blobs, traces — no stable `EditDecisionList` / `RenderManifest` schemas.
4. **Search = selection:** `director_gate.evaluate_asset` scores **metadata text**, not pixels.
5. **Motion = Ken Burns / punch_in:** `ai_visuals.image_to_motion_clip`, `render` zoompan, retention `controlled_punch_in` — primary “editing language.”
6. **Scene schedule vs story beats:** `plan_scene_schedule` still duration-driven; Director beats approximate story but render still concatenates clips with xfade.
7. **Provider coupling:** Pexels/Pixabay/Mixkit inside `stock_media.py`; no `MediaProvider` interface; 429 storms observed in E2E.
8. **Motion graphics:** local PIL in `beat_recovery`, not Remotion primitives; Remotion exists but unused by `/generate`.
9. **No FinalVideoCritic:** gates use traces + heuristics, not frame inspection of final MP4.
10. **Dual split-screen sibling** always attempted — extra cost/noise for review packages.

---

## 6. Slideshow-producing behaviors (must remove or demote in V2)

| Behavior | Where | Effect |
|----------|--------|--------|
| Ken Burns on stills | `ai_visuals.image_to_motion_clip`, `render` zoompan | Still + zoom counted as “video shot” |
| Live zoompan on stock mp4 | `render.py` when `apply_zoompan` | Motion without new information |
| Same-asset punch_in / crop_zoom | `phase3_retention`, `director._apply_visual_change_reuse` | Fake variety; VIU unchanged |
| “Retention events” | `phase3_retention.plan_retention_events` | Transform-as-attention without new assets |
| Metadata-first accept | `director_gate.evaluate_asset` | Wrong entity / generic luxury can pass if tags match |
| Heuristic luxury/finance queries | `director_planner` money beats | Seeds generic wealth B-roll |
| Random among top-N photos | `ai_visuals`, `split_screen` satisfying clip | Non-deterministic filler |
| Gradient / Pollinations fallback | `ai_visuals.generate_ai_image` | Decorative non-documentary frames |
| Clip loop / reuse to fill duration | `render` stream loop + reuse ratio | Same asset stretched across timeline |

**Mitigations already present (insufficient alone):** no ungated stock fill after Director miss; `fallback_on_empty=False` on product paths; NoSlideshowGate FAIL; source-asset counting; domain lock on script; beat recovery.

---

## 7. Unsafe fallback behaviors

| Fallback | Risk | Current control |
|----------|------|-----------------|
| `ALLOW_STOCK_FALLBACK=true` | Stock after AI miss | On by default |
| Empty stock → gradient clips | Slideshow filler | Disabled on main product calls (`fallback_on_empty=False`) |
| Pexels 429 → retry storms | Hang / timeout (seen in recovery E2Es) | Partial early-break in recovery; first-pass still heavy |
| Verifier/LLM outage | Thin or collapsed story | Script quality fail-closed / REVIEW; replacement research |
| Unknown visual relevance | Treated as usable if metadata gate passes | **No VisualVerifier — UNKNOWN≈ACCEPT today** |
| Uncovered beat → prior asset | False coverage | Blocked for important roles; recovery may still leave UNCOVERED |

---

## 8. Provider limitations

| Provider | Role | Limits |
|----------|------|--------|
| Pexels video/photo | Primary stock | Rate limits (429); metadata-only relevance |
| Pixabay | Secondary stock | Same semantic weakness |
| Mixkit | Tertiary, no key | Generic stock |
| Wikipedia / Commons | Person archive + fact evidence | Portrait OK; not full video archive |
| Fal Flux | AI still → Ken Burns | Cost; synthetic; not authentic evidence |
| Pollinations | Soft AI fallback | Low quality decorative |
| Kling / Fal video | Legacy engines | Not compose default |
| Internet Archive | **Not integrated** | V2 target |
| Remotion | Experimental motion | Not wired to `/generate` EDL |
| Multimodal embeddings / VLM | **Absent** | V2 target |

Provenance today: partial (`provider`, `asset_id`, URL in metadata). **No license/attribution manifest** for final package.

---

## 9. Tests / traces / job state (inventory)

**Tests (relevant):** `test_director*`, `test_director_gate_regression`, `test_script_quality`, `test_no_slideshow`, `test_source_diversity`, `test_beat_recovery`, `test_phase3*`, `test_render`, `test_pipeline_pending`, `test_pending_endpoint`, `publishers/test_*`.

**Root reports:** `SCRIPT_QUALITY_*`, `NO_SLIDESHOW_*`, `SOURCE_DIVERSITY_*`, `UNCOVERED_BEAT_RECOVERY_*`. No prior `DOCUMENTARY_ENGINE_V2_*`.

**Job state:** SQLite (`generating` | `awaiting_approval` | `publishing` | `done` | `failed`) + `pending.json` mirror. Blocking clear must include `generating` (stuck jobs caused 409s).

**Traces written under `/data/media`:** `SCRIPT_QUALITY_TRACE_*`, `SOURCE_DIVERSITY_TRACE_*`, `UNCOVERED_BEAT_RECOVERY_TRACE_*` (alias).

---

## 10. Gap analysis vs Documentary Engine V2 brief

| V2 requirement | Current state |
|----------------|---------------|
| STORY → SHOT REQUIREMENT → SEARCH → PREFILTER → **VISUAL ANALYSIS** → RERANK → SELECT | Stops at metadata gate |
| Canonical schemas (VerifiedStory, EDL, RenderManifest, …) | Loose dicts + dataclasses scattered |
| MediaProvider abstraction + provenance/license | Coupled stock_media; weak license |
| MultimodalReranker + VisualVerifier | Missing |
| UNKNOWN ≠ ACCEPT | Missing (fail-open on visual unknown) |
| Remotion for evidence graphics | PIL hierarchy only; Remotion unused |
| GeneratedVideoProvider (non-default) | Fal still+KB / optional Kling |
| EditDecisionList drives render | Render invents zoompan/xfade independently |
| FinalVideoCritic + targeted repair | Missing |
| Production telemetry contract | Partial traces; no ProductionManifest schema |
| Diverse documentary benchmark | Rolex-heavy regressions only |
| Video-first documentary feel | Still slideshow-prone under stock/Director transforms |

---

## 11. Migration risks

1. **Turning off Ken Burns / punch_in** without replacement visuals → more UNCOVERED / REVIEW_REQUIRED until VisualVerifier + providers mature.
2. **Enabling VisualVerifier** (cloud VLM) → cost + latency; need fail-closed REVIEW policy.
3. **Provider abstraction** mid-flight → regression on Pexels paths and used_clips dedup.
4. **EDL-driven render** → must not break mux duration, ASS burn-in, BGM duck.
5. **Default `DIRECTOR_ENABLED=false`** → V2 must decide: Director becomes default documentary path, or replace both legacy and Director with V2 behind one flag.
6. **Remotion in Docker** — currently host-only; motion graphics may stay PIL/FFmpeg until Remotion is containerized.
7. **Pexels rate limits** — multimodal preview download will worsen unless staged budgets + caching land early.
8. **Do not break:** AIRouter, MİKO, publishers, Telegram, credentials, fact layer, TTS, captions, music vocals policy.

---

## 12. Recommended V2 entry (after human approval)

Per brief §41 — **do not big-bang**. Proposed next implementation checkpoint:

**Stage A only (after approval):**  
canonical schemas + adapters + ProductionManifest telemetry + feature flag `DOCUMENTARY_ENGINE_V2` (default off) so existing `/generate` still works.

Then B→G as specified. **No publish. No AIRouter redesign. No Bonsai. No MİKO changes.**

---

## 13. Baseline verdict

The repo can already:

- verify scripts,
- gate metadata relevance,
- track source-asset / VIU honesty,
- recover some uncovered beats with evidence diagrams,
- render and hold for Telegram approval.

It **cannot yet** guarantee a mini-documentary because:

**candidates are selected without looking at pixels**,  
**motion is largely Ken Burns / punch-in**, and  
**render is not driven by an EditDecisionList**.

That is the structural gap Documentary Engine V2 must close.

---

**STOP before code.** Awaiting human approval to begin Stage A (schemas + telemetry + flag) only.
