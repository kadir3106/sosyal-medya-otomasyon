# DOCUMENTARY ENGINE V2 — STAGE F.1 TARGETED REPAIR REPORT

- Job: `sf120260928-104804_2cfd04`
- Parent regression job: `sf20260925-002306_af460d`
- Topic: Who really owns Rolex?
- Verdict: **REVIEW_REQUIRED — human must watch the repaired MP4**
- Publish/freeze/global V2 enablement: **NO**

## Root causes and targeted fixes

- Static hook: replaced the prior still with separately acquired, source-recorded Rolex motion footage.
- Caption sentence merge: reused the punctuation-safe semantic caption cues and extended the final cue to the narration clock.
- Founder gap: filled with a source-recorded historical Hans Wilsdorf portrait; no unrelated stock or generated person footage.
- Early/obscured ownership graphic: regenerated only the ownership/reveal beats with larger labels, a 30% bottom caption-safe band, no internal claim IDs, and source-bound facts.
- SL QUARTZ/Omega: removed from all selections; strict visible-brand conflict is now a hard Stage C rejection.
- Early visual/caption termination: the final EDL decision and final caption now end on the narration clock; no `-shortest` is used.
- Provenance: external assets carry source URLs and explicit reusable/public-domain status; UNKNOWN+blank URL is no longer production PASS.
- No-slideshow: transform-only stills do not create new VIUs, and actual rendered freeze/tail-hold diagnostics feed the gate.

## Files changed

- `app/documentary_v2/verifier/reason_codes.py`
- `app/documentary_v2/verifier/prompt.py`
- `app/documentary_v2/verifier/decision.py`
- `app/documentary_v2/assembly/timeline.py`
- `app/documentary_v2/assembly/technical_qa.py`
- `app/documentary_v2/assembly/orchestrator.py`
- `app/documentary_v2/recovery/theme.py`
- `app/documentary_v2/recovery/renderer.py`
- `app/subtitles.py`
- `scripts/stage_f_real_e2e.py`
- `scripts/stage_f_complete.py`
- `scripts/stage_f1_targeted_repair.py`
- `tests/test_documentary_v2_stage_f1.py`
- `tests/test_documentary_v2_stage_f.py`
- `video-output/stage_f_repair_assets/rolex_6230465_hd.mp4` (official Pexels API acquisition; provenance recorded)

## Tests

- TDD RED: 9 failed / 1 passed before implementation (the initial freeze probe environment issue was corrected, then failed on the missing metric as intended).
- Stage F.1 regression tests: 10/10 passed after implementation.
- Focused Stage C/F/subtitle tests: 16/16 passed after implementation.
- Full impacted suite: 101/101 passed (15 pre-existing Pillow deprecation warnings).

## Package metrics

- Duration: 25.5 s
- Beat count: 6
- Shot count: 6
- Unique source assets / VIUs: 6 / 6
- Seconds by class: `{"real_entity_video": 0.0, "archive_video": 0.0, "stock_video": 12.39, "motion_graphic": 8.9, "synthetic_video": 0.0, "archive_still": 4.2, "evidence_document": 0.0}`
- Real/entity/archive/document/motion/illustrative seconds: 12.39 / 8.00 / 4.20 / 0.00 / 8.90 / 4.39.
- Uncovered important beats: `[]`
- Wrong-entity rejections: 0 live; 2 deterministic regression rejects (Omega, SL QUARTZ).
- Final visual PTS / narration end: 25.488 / 25.488 s
- Final caption end / narration end: 25.480 / 25.488 s (8 ms tolerance).
- Freeze diagnostics: longest=3.5 s, tail=0.0 s, intervals=[{'start_sec': 0.0, 'end_sec': 1.0}, {'start_sec': 3.5, 'end_sec': 7.0}, {'start_sec': 7.0, 'end_sec': 8.0}, {'start_sec': 8.0, 'end_sec': 9.5}, {'start_sec': 9.5, 'end_sec': 11.5}, {'start_sec': 11.5, 'end_sec': 12.5}, {'start_sec': 12.5, 'end_sec': 14.5}, {'start_sec': 14.5, 'end_sec': 16.0}, {'start_sec': 16.0, 'end_sec': 17.0}]
- Provenance/license gate: PASS
- No-slideshow gate: REVIEW_REQUIRED

## Visual verification and critic

- Stage C decisions: `{"cand:pexels:6230465": "UNCERTAIN", "cand:commons:hans_wilsdorf": "UNCERTAIN", "cand:pexels:8322145": "UNCERTAIN", "cand:pexels:17197593": "ACCEPT"}`
- FinalVideoCritic: **REVIEW_REQUIRED**; notes: critic_vlm_error:RATE_LIMITED
- Critic provider/model/calls: direct_groq / qwen/qwen3.8-27b / 0
- Pixels inspected: **YES** — source contact sheet and final rendered frame contact sheet were inspected; the critic result above is recorded separately.

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

- Final acceptance remains REVIEW_REQUIRED until a human watches the complete repaired MP4.
- The freeze probe reports one 3.5 s interval during the authentic founder portrait; this does not dominate the 25.5 s video, but intentionally keeps the no-slideshow gate at REVIEW_REQUIRED for human judgment.
- Generic watchmaking footage is intentionally labeled illustrative and must not be read as Rolex factory evidence.
- Any critic rate limit/unavailability remains REVIEW_REQUIRED; it is never converted into PASS.

## Artifacts

- MP4: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F1_REAL_sf120260928-104804_2cfd04.mp4`
- EDL: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F1_EDL_sf120260928-104804_2cfd04.json`
- MANIFEST: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F1_MANIFEST_sf120260928-104804_2cfd04.json`
- TRACE: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F1_TRACE_sf120260928-104804_2cfd04.json`
- ATTRIBUTION: `C:\Projects\sosyal-medya-otomasyon\video-worker\video-output\DOCUMENTARY_ENGINE_V2_STAGE_F1_ATTRIBUTION_sf120260928-104804_2cfd04.json`
