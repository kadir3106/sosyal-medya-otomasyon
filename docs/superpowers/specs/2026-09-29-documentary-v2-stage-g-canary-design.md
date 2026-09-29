# Documentary Engine V2 Stage G Canary Design

## Status

Approved in chat on 2026-09-29. Stage G validates generalization without changing production routing or the accepted Stage F.1.1 artifact.

## Objective

Build a thin, explicit, fail-closed canary orchestration layer around the existing `run_topic_review` and Stage F assembly flow. Run five evidence-rich topics across genuinely different documentary story types, produce a complete diagnostic package for every job, require real-MP4 human review, and make one aggregate readiness decision without globally enabling V2.

Stage G succeeds only when at least three genuinely different story types are human-accepted and all hard-fail invariants remain intact.

## Non-goals

Stage G does not:

- alter the accepted Stage F.1.1 MP4 or its lineage;
- create a second research, director, assembly, or rendering engine;
- connect V2 to `/generate`, queues, schedulers, publishers, or production routing;
- enable global V2, auto-publish, or controlled production opt-in;
- modify MIKO, AIRouter, Bonsai, local generation, analytics implementation, or legacy production behavior;
- redesign audio, captions, media providers, or recovery unless a canary exposes a separately approved systemic defect;
- manually inject final scripts or assets.

## Baseline freeze

Create `DOCUMENTARY_ENGINE_V2_ACCEPTED_BASELINE.md` if it does not exist. It records:

- accepted job: `sf1120260928-185746_d79a71`;
- accepted MP4: `DOCUMENTARY_ENGINE_V2_STAGE_F11_REAL_sf1120260928-185746_d79a71.mp4`;
- acceptance date and human decision;
- focused tests and the absence of a claimed full-repository pass;
- known LOW issues: generic opening wording and the sparse final portion of the ownership-history graphic;
- regression invariants listed in the Stage G brief.

The baseline artifact and existing Stage F.1.1 report are read-only inputs to Stage G.

## Explicit canary mode

Add `DOCUMENTARY_V2_CANARY` to `PipelineMode`, but do not expose it through an environment-only switch.

`resolve_pipeline_mode` accepts an explicit programmatic `canary` argument. It returns `DOCUMENTARY_V2_CANARY` only when that argument is true. Existing calls that omit the argument retain current legacy behavior. `pipeline_mode_diagnostics` may report canary state only when explicitly asked; normal startup diagnostics remain unchanged.

The Stage G CLI is the only Stage G entry point. It calls the canary orchestrator directly and never imports or invokes publishing code.

## Canary suite definition

Keep the suite definition as data rather than executable policy. Each entry contains:

- `topic`;
- `story_type`;
- `selection_rationale`;
- required generalization dimensions such as entity, person, archive, document, process, location, and graphics;
- optional alternative topic candidates for preflight rejection.

The target suite covers five distinct categories:

1. named company / ownership;
2. historical person / founder story;
3. real physical process;
4. historical location / place;
5. abstract business or financial mechanism.

Topic names may be selected and recorded before execution. Final scripts, claims, sources, and media are not supplied by the suite. They must come from the existing research, fact, beat-planning, retrieval, verification, recovery, and assembly flow.

## Job lifecycle

Each canary gets an independent path-safe job ID and directory under:

`video-worker/video-output/stage_g/<jobid>/`

The orchestrator performs:

1. suite-entry validation;
2. explicit canary-mode resolution;
3. call to `run_topic_review` with the job budget and isolated media directory;
4. normalization of Stage F/topic-review artifacts into Stage G filenames;
5. fail-closed gate evaluation;
6. failure-cluster classification;
7. human-review template creation with decision `NOT_RUN`;
8. aggregate draft update.

The existing topic-review function remains responsible for real research, verified story creation, semantic beat planning, TTS, captions, director acquisition, verification, recovery, EDL assembly, render, critic, and technical gates.

## Artifact contract

Every job produces these Stage G paths, even if no MP4 is rendered:

- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_<jobid>.mp4` when rendering succeeds;
- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_EDL_<jobid>.json`;
- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_MANIFEST_<jobid>.json`;
- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_TRACE_<jobid>.json`;
- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_ATTRIBUTION_<jobid>.json`;
- `DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_HUMAN_REVIEW_<jobid>.md`.

When an upstream artifact does not exist, the Stage G counterpart explicitly records `artifact_status: NOT_PRODUCED`, the failed stage, the error, gates known at failure time, and the failure clusters. It does not invent EDL decisions, provenance, licenses, verification results, or human findings.

Successful Stage F artifacts are parsed and rewritten with Stage G lineage fields rather than copied as opaque files. The MP4 may be renamed within its new job directory. Existing F.1.1 files are never moved or overwritten.

## Fail-closed acceptance

A canary cannot receive automated PASS when any of these conditions holds:

- VLM is unavailable, rate-limited, or did not inspect actual pixels where required;
- a required entity conflicts with the visible entity or remains uncertain;
- an important beat is uncovered;
- context, illustration, generic process footage, or synthetic media is presented as factual evidence;
- an external selected asset has unknown/restricted provenance or lacks a source URL;
- the visual timeline or final caption ends before narration;
- a frozen tail hides missing coverage;
- slideshow is the primary visual language;
- an unresolved HIGH critic or human issue remains;
- human review is incomplete;
- manual final-script or final-asset intervention occurred.

There is no silent fallback to legacy stock. An incomplete V2 canary returns `REVIEW_REQUIRED` or `FAIL` and retains its diagnostics.

## Human review

Generation always writes a human-review template with `Decision: NOT_RUN`. Stage G cannot infer human acceptance from automated gates.

Each produced MP4 is watched and reviewed for:

- factual and entity correctness;
- evidence semantics;
- narration/visual alignment;
- beat and VIU progression;
- generic filler and repetition;
- captions and graphic readability;
- timeline and final-tail integrity;
- slideshow dominance;
- hook, payoff, transitions, vertical composition, and overall quality;
- subjective audio when playback is available; otherwise `UNAVAILABLE`.

The completed review records timestamped HIGH, MEDIUM, and LOW findings; dimension decisions; overall human quality; and whether manual intervention was required.

## Failure clustering

Map errors and gate failures deterministically to one or more clusters:

- `ENTITY_SELECTION`
- `ARCHIVE_RETRIEVAL`
- `PROCESS_VISUAL`
- `PROVENANCE`
- `CAPTION`
- `GRAPHIC_DENSITY`
- `TIMELINE`
- `STORY`
- `VLM_RATE_LIMIT`
- `GENERIC_BROLL`

Unknown failures remain visible as `UNCLASSIFIED`; they are never coerced into a successful category.

## Aggregate scorecard

Create:

- `DOCUMENTARY_ENGINE_V2_STAGE_G_REPORT.md`
- `DOCUMENTARY_ENGINE_V2_STAGE_G_SCORECARD.json`

The scorecard reports each dimension independently:

- factual quality;
- story quality;
- entity safety;
- visual coverage;
- evidence integrity;
- provenance;
- no-slideshow;
- caption quality;
- timeline integrity;
- final human quality.

It also includes the requested counts, averages, VLM activity, costs, manual intervention, failure clusters, and a generalization matrix. It does not calculate a single composite score.

## Readiness decision

The finalizer returns one of:

- `CANARY_PASS`: at least three different story types are human-accepted, the majority of accepted canaries are GOOD/PREMIUM, and no accepted canary violates a hard-fail invariant;
- `CANARY_PARTIAL`: the architecture works but one or more systemic or topic-specific issues require targeted repair;
- `CANARY_FAIL`: V2 does not provide sufficient generalization evidence.

Five jobs are targeted. A failed canary remains part of the scorecard. With only three produced videos, all three must be accepted. No result enables production. A `CANARY_PASS` recommends only a future controlled production opt-in proposal.

## Telemetry

Use data already emitted by the director, assembly, critic, TTS, and technical QA. Record, when available:

- LLM and VLM calls;
- provider queries;
- downloads/materializations;
- accepted, rejected, and uncertain candidates;
- recovery attempts;
- render and critic latency;
- estimated API, TTS, video-generation, and total cost;
- TTS provider/fallback and music selection/mix data.

Missing telemetry remains null or explicitly unavailable. Stage G does not add MIKO analytics.

## Minimal file boundary

Expected source changes are limited to:

- `DOCUMENTARY_ENGINE_V2_ACCEPTED_BASELINE.md`
- `video-worker/app/documentary_v2/schemas.py`
- `video-worker/app/documentary_v2/pipeline_mode.py`
- new `video-worker/app/documentary_v2/canary.py`
- new `video-worker/scripts/stage_g_canary.py`
- new Stage G suite data file
- new `video-worker/tests/test_documentary_v2_stage_g.py`
- generated Stage G job and aggregate artifacts.

No changes are planned for `main.py`, the production pipeline, publishers, queues, schedulers, MIKO, AIRouter, Bonsai, or local generation.

## Testing strategy

Use test-driven development. Required red-green regressions cover:

- explicit-only canary mode and unchanged default modes;
- publish disabled for every outcome;
- complete diagnostic package on early and late failures;
- no legacy fallback;
- rate-limit, provenance, coverage, entity, evidence, timeline, caption, slideshow, HIGH-issue, manual-intervention, and incomplete-human-review fail-closed behavior;
- deterministic failure clustering;
- no `CANARY_PASS` below three distinct accepted story types;
- no aggregate single-score field;
- generalization matrix and per-dimension results;
- baseline immutability.

After Stage G tests pass, run the focused F.1.1 and topic-review regression suites. Run the broader repository suite where practical, and report any interruption or unrelated failure exactly rather than claiming an unobserved pass.

## Working-tree safety

Work in the current checkout because the accepted V2/F.1.1 implementation includes uncommitted and untracked files that a new worktree would not contain. Use an exact file allowlist. Never reset, clean, checkout, or overwrite unrelated files. Stage only named Stage G/spec files when a commit is required, and report every changed file at the end.

