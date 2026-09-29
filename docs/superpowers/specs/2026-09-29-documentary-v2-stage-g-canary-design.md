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

### Publish hard invariant

Stage G is permanently non-publishing. Its public API, CLI, and runner MUST reject `publish=True` before job execution and MUST NOT infer publishing behavior from environment or configuration defaults. At every Stage G-to-downstream pipeline boundary, the orchestrator MUST pass `publish=False` explicitly; any reused callable with a `publish` parameter MUST receive `publish=False`, not its default. Publisher entry points MUST NOT appear in the Stage G call graph. If a required downstream path cannot guarantee non-publishing execution, the job MUST fail closed before that path executes.

The existing `run_topic_review` and `run_stage_f_pipeline` boundaries must expose or preserve an explicit `publish=False` contract so this invariant is enforceable without changing production routing. Helpers without publishing capability are not given a new `publish` parameter solely for Stage G.

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

Preflight topic rejection is a recorded canary outcome. The topic's source and visualizability assessment must be recorded before TTS or rendering; unsupported central claims or a story dependent only on generic filler reject the job at preflight.

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

### Manual intervention and autonomy

Set `manual_intervention_required: true` when a human injects, replaces, or edits a final production decision: final script, selected asset, shot selection, EDL creative decision, or evidence supplied solely to make the job pass. Human review, approval or rejection, diagnosis, and rerunning an existing autonomous path do not count as manual intervention.

A manually intervened job remains in the report with its actual human quality result and diagnostics, but MUST NOT count toward the autonomous canary PASS count, accepted story-type count, three distinct successful story types, generalization evidence, or autonomy success metrics. Every generalization-matrix entry records `manual_intervention_required: true/false` and `counts_as_autonomous_evidence: true/false`. The invariant is `manual_intervention_required == true => counts_as_autonomous_evidence == false`.

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

The following error/gate-code mapping is normative:

| Codes | Cluster |
| --- | --- |
| `WRONG_ENTITY`, `ENTITY_UNCERTAIN`, `ENTITY_CONFLICT`, `NAMED_ENTITY_REJECT` | `ENTITY_SELECTION` |
| `FOUNDER_ARCHIVE_MISSING`, `PERSON_ARCHIVE_MISSING`, `ARCHIVE_NOT_FOUND`, `ARCHIVE_VERIFY_FAILED` | `ARCHIVE_RETRIEVAL` |
| `PROCESS_ENTITY_MISMATCH`, `PROCESS_VISUAL_MISSING`, `GENERIC_PROCESS_AS_ENTITY`, `GENERIC_PROCESS_AS_EVIDENCE` | `PROCESS_VISUAL` |
| `LICENSE_UNKNOWN`, `SOURCE_URL_MISSING`, `ATTRIBUTION_INVALID`, `PROVENANCE_INCOMPLETE` | `PROVENANCE` |
| `CAPTION_END_EARLY`, `CAPTION_MISSING`, `CAPTION_RENDER_FAILURE`, `CAPTION_SAFE_AREA_FAILURE` | `CAPTION` |
| `GRAPHIC_TEXT_TOO_SMALL`, `GRAPHIC_DENSITY_FAILURE`, `GRAPHIC_READABILITY_FAILURE` | `GRAPHIC_DENSITY` |
| `VISUAL_END_EARLY`, `FROZEN_TAIL`, `EDL_GAP`, `MUX_DURATION_MISMATCH` | `TIMELINE` |
| `STORY_QUALITY_FAIL`, `STORY_CONSISTENCY_FAIL`, `UNSUPPORTED_CENTRAL_CLAIM`, `TOPIC_PREFLIGHT_REJECT` | `STORY` |
| `VLM_RATE_LIMIT`, `VLM_UNAVAILABLE`, `VLM_TIMEOUT`, `VISION_PROVIDER_FAILURE` | `VLM_RATE_LIMIT` |
| `UNRELATED_STOCK`, `GENERIC_FILLER`, `GENERIC_BROLL_DOMINANT`, `WEAK_VISUAL_ALIGNMENT` | `GENERIC_BROLL` |
| Any unmapped code | `UNCLASSIFIED` |

A job MAY have multiple clusters. Preserve all applicable clusters in `all_clusters`; never force one root cause when multiple are evidenced. Choose `primary_cluster` from those clusters by this priority, then lexicographically within a priority level: (1) `ENTITY_SELECTION`, `PROVENANCE`; (2) `STORY`, `PROCESS_VISUAL`; (3) `TIMELINE`, `CAPTION`, `GRAPHIC_DENSITY`; (4) `GENERIC_BROLL`, `ARCHIVE_RETRIEVAL`; (5) `VLM_RATE_LIMIT`; (6) `UNCLASSIFIED`. The report retains both `primary_cluster` and `all_clusters`.

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

Define `AUTONOMOUS_ACCEPTED_JOB` as a job with a successfully produced MP4, completed human review and human decision `PASS`, `manual_intervention_required == false`, no unresolved HIGH issue or hard-fail gate, acceptable provenance, entity safety, evidence integrity, and timeline/caption integrity, and `dominant_slideshow == false`.

`DISTINCT_ACCEPTED_STORY_TYPES` is the set of unique `story_type` values among autonomous accepted jobs. `HIGH_QUALITY_ACCEPTED_JOB` is an autonomous accepted job with human quality `GOOD` or `PREMIUM`. `PENDING_HUMAN_JOB` has an MP4 but human review is `NOT_RUN` or incomplete. `ACCEPTABLE` and `WEAK` do not count as high quality. Automated critic output MUST NOT fabricate human review.

Evaluate the decisions in the order below. `CANARY_PARTIAL` applies only when no `CANARY_FAIL` condition holds. Pending human jobs never contribute to PASS.

The finalizer returns one of:

- `CANARY_PASS`: at least three autonomous accepted jobs represent at least three distinct story types; every job used as acceptance evidence has completed human review; accepted jobs have zero wrong-entity, misleading-evidence, timeline/final-caption, provenance, or dominant-slideshow hard failures and zero unresolved HIGH issues; no manually intervened job is used as acceptance evidence; and `HIGH_QUALITY_ACCEPTED_JOB / AUTONOMOUS_ACCEPTED_JOB > 0.5`.
- `CANARY_PARTIAL`, if PASS is false and FAIL conditions are absent: at least one autonomous accepted job exists but PASS evidence is insufficient; or potentially valid jobs are pending human review; or infrastructure/provider limitations (such as `VLM_RATE_LIMIT`) mainly block the suite without reaching the systemic creative/safety threshold; or fewer than three distinct story types are autonomously accepted while at least one demonstrates valid autonomous success.
- `CANARY_FAIL`, if PASS is false: zero autonomous accepted jobs and at least one completed canary failed for a non-infrastructure creative/safety/integrity reason; or the same systemic hard-failure cluster occurs in at least two distinct story types; or an implementation defect violates Stage G safety boundaries (publishing attempted, silent legacy fallback, fabricated provenance or human review, or production isolation violation); or the configured real test set is exhausted without any autonomous completion.

For deterministic classification, “mainly blocked by infrastructure/provider limitations” means `VLM_RATE_LIMIT` is the most frequent `primary_cluster` among completed failed jobs, with no tie, while no systemic creative/safety threshold is met. A job that is pending human review is not a completed failure. The systemic creative/safety threshold counts a hard-failure cluster across at least two distinct story types; `VLM_RATE_LIMIT` alone is an infrastructure limitation, not a creative/safety cluster. `CANARY_FAIL` conditions take precedence over `CANARY_PARTIAL` conditions. Before the configured test set is exhausted, the aggregate is a draft; it may record `PENDING` when none of the final-decision predicates applies, and MUST NOT claim success.

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
- `video-worker/app/documentary_v2/review_runner.py` (explicit non-publishing boundary)
- `video-worker/app/documentary_v2/assembly/orchestrator.py` (explicit non-publishing boundary)
- new `video-worker/app/documentary_v2/canary.py`
- new `video-worker/scripts/stage_g_canary.py`
- new Stage G suite data file
- new `video-worker/tests/test_documentary_v2_stage_g.py`
- generated Stage G job and aggregate artifacts.

No changes are planned for `main.py`, the production pipeline, publishers, queues, schedulers, MIKO, AIRouter, Bonsai, or local generation.

## Testing strategy

Use test-driven development. Required red-green regressions cover:

- explicit-only canary mode and unchanged default modes;
- `publish=True` rejected before execution, omitted publish unable to become true through environment/config, every downstream publish-capable mock called with `publish=False`, and publisher entry points never called;
- complete diagnostic package on early and late failures;
- no legacy fallback;
- rate-limit, provenance, coverage, entity, evidence, timeline, caption, slideshow, HIGH-issue, manual-intervention, and incomplete-human-review fail-closed behavior;
- deterministic failure clustering;
- manual-intervention classification and exclusion from autonomy/generalization counts;
- no `CANARY_PASS` below three distinct accepted story types;
- no aggregate single-score field;
- generalization matrix and per-dimension results;
- baseline immutability.

After Stage G tests pass, run the focused F.1.1 and topic-review regression suites. Run the broader repository suite where practical, and report any interruption or unrelated failure exactly rather than claiming an unobserved pass.

## Working-tree safety

Work in the current checkout because the accepted V2/F.1.1 implementation includes uncommitted and untracked files that a new worktree would not contain. Use an exact file allowlist. Never reset, clean, checkout, or overwrite unrelated files. Stage only named Stage G/spec files when a commit is required, and report every changed file at the end.
