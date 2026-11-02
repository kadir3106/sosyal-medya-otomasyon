# DOCUMENTARY ENGINE V2 — STAGE F.1.1 FINAL TARGETED REPAIR REPORT

- Job: `sf1120260928-185746_d79a71`
- Parent F.1 job: `sf120260928-104804_2cfd04`
- Original Stage F regression: `sf20260925-002306_af460d`
- Topic: Who really owns Rolex?
- Verdict: **REVIEW_REQUIRED — human must watch the complete MP4**
- Publish/freeze/global V2 enablement: **NO**

## F.1 → F.1.1 delta

- Previous review: HIGH 1 / MEDIUM 3 / LOW 1; slideshow BORDERLINE.
- Remaining sampled-frame findings: **HIGH 0 / MEDIUM 0 / LOW 1** (the intentionally unchanged generic hook wording); complete-video human watch remains required.
- 16.02–20.41 root cause: F.1 cleared Rolex from required entities, disabled strict mode, and selected generic watchmaking as illustration without a rendered disclosure.
- Repair: important named-entity process beats retain strict entity requirements in the shared shot director; illustration cannot satisfy ENTITY/AUTHENTIC_CONTEXT requirements.
- Replacement: verified Pexels Rolex macro `6230464`, role `ENTITY / AUTHENTIC_CONTEXT`.
- Manufacturing evidence separation: the macro is **not** manufacturing/process evidence; the factual claim remains source-bound to the official Rolex watchmaking source in EDL/manifest/trace.
- Illustrative disclosure: **NOT APPLICABLE** because no generic footage is used in the repaired beat.
- Founder portrait: unchanged and preserved as the accepted Hans Wilsdorf archive still.
- Ownership graphics: denser mobile hierarchy, source-bound explanatory labeling, restrained progressive reveal; no claim IDs or unsupported evidence implication.
- Ownership/reveal durations: 4.480 / 4.420 s.
- Caption style: font 76, outline 4, vertical margin 420; dialogue text/timing preserved.

## Exact files changed

- `app/documentary_v2/director/shot_director.py`
- `app/documentary_v2/verifier/decision.py`
- `app/documentary_v2/recovery/renderer.py`
- `app/subtitles.py`
- `scripts/stage_f11_targeted_repair.py`
- `tests/test_documentary_v2_stage_f1.py`
- `video-output/stage_f_repair_assets/rolex_6230464_hd.mp4`

## Tests

- TDD RED: 3 shared-flow regressions failed for the intended reasons; 10 prior F.1 tests passed.
- Shared-flow GREEN after minimum fix: 13/13.
- Ownership density RED: 2/2 sparse graphic cases failed below threshold.
- F.1.1 focused GREEN after graphic polish: 15/15.
- Fresh impacted Stage C/F/F.1 suite: **49/49 passed** (14 deprecation warnings; 6.82 s).
- A repository-wide pytest run was attempted but intentionally stopped after exceeding the practical validation window in long external/media-dependent cases. It emitted failure markers before interruption and produced no final summary, so this report does **not** claim a full-repository PASS.

## Package metrics

- Duration: 25.5 s
- Beat count / shot count: 6 / 6
- Unique source assets / VIUs: 6 / 6
- Seconds by class: `{"real_entity_video": 0.0, "archive_video": 0.0, "stock_video": 12.39, "motion_graphic": 8.9, "synthetic_video": 0.0, "archive_still": 4.2, "evidence_document": 0.0}`
- Entity seconds: 12.388; illustrative seconds: 0.000.
- Uncovered important beats: `[]`
- Process EDL role: `AUTHENTIC_CONTEXT_REQUIRED`; asset: `cand:pexels:6230464`.
- Process Stage C result: `UNCERTAIN` because the live verifier did not return a usable semantic verdict; provenance plus human pixel inspection confirm the visible asset is the recorded Rolex candidate. It remains context, not manufacturing evidence.
- Wrong-entity rejections: 0 live; deterministic Omega/Speedmaster/SL QUARTZ regressions retained.
- Final visual PTS / narration end: 25.488 / 25.488 s.
- Final caption end / narration end: 25.480 / 25.488 s.
- Freeze diagnostics: longest=3.5 s, tail=0.0 s, intervals=[{'start_sec': 0.0, 'end_sec': 1.0}, {'start_sec': 3.5, 'end_sec': 7.0}, {'start_sec': 7.0, 'end_sec': 8.0}, {'start_sec': 8.0, 'end_sec': 9.0}, {'start_sec': 9.0, 'end_sec': 11.5}, {'start_sec': 11.5, 'end_sec': 12.5}, {'start_sec': 12.5, 'end_sec': 13.5}, {'start_sec': 13.5, 'end_sec': 14.5}, {'start_sec': 14.5, 'end_sec': 16.0}, {'start_sec': 16.0, 'end_sec': 17.0}]
- No-slideshow gate: REVIEW_REQUIRED
- Provenance/license gate: PASS

## Critic and inspection

- FinalVideoCritic: **REVIEW_REQUIRED**; notes: canonical MP4 frames were submitted successfully, then Direct Groq returned `RATE_LIMITED`.
- Critic provider/model/calls: direct_groq / qwen/qwen3.8-27b / 1
- Pixels inspected: **YES** — source contact sheet plus final frames at 1.5, 4.5, 8.0, 10.5, 12.5, 15.0, 16.5, 18.5, 20.8, 24.5, and 25.3 seconds were inspected. No Omega, Speedmaster, SL QUARTZ, missing final caption, graphic-label collision, or frozen final tail was observed in those samples.
- Audio subjective review: **AUDIO_SUBJECTIVE_REVIEW_UNAVAILABLE**; technical metrics only.

## Gates

- FinalVideoQualityGate: **REVIEW_REQUIRED**
- FactQualityGate: **PASS**
- StoryQualityGate: **PASS**
- StoryConsistencyGate: **PASS**
- BeatPlanGate: **PASS**
- LicenseProvenanceGate: **PASS**
- VisualCoverageGate: **PASS**
- TechnicalRenderQA: **PASS**
- NoSlideshowQualityGate: **REVIEW_REQUIRED**

## Unresolved issues

- Final acceptance remains human-only after watching the complete repaired MP4.
- Direct Groq was rate-limited after one real pixel-bearing call; the result remains REVIEW_REQUIRED and was not converted to PASS.
- Product macro supports entity/authentic context only; it does not visually prove the manufacturing claim.
- Complete human playback, including subjective audio review, is still outstanding.

## Artifacts

- MP4: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F11_REAL_sf1120260928-185746_d79a71.mp4`
- EDL: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F11_EDL_sf1120260928-185746_d79a71.json`
- MANIFEST: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F11_MANIFEST_sf1120260928-185746_d79a71.json`
- TRACE: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F11_TRACE_sf1120260928-185746_d79a71.json`
- ATTRIBUTION: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F11_ATTRIBUTION_sf1120260928-185746_d79a71.json`
