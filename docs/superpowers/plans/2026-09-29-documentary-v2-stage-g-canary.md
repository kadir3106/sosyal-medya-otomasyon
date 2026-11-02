# Documentary Engine V2 Stage G Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run five isolated, unpublished documentary canaries and issue a human-reviewed, deterministic generalization decision with complete diagnostics for every job.

**Architecture:** Add an explicit canary mode and a thin orchestration layer around `run_topic_review` and `run_stage_f_pipeline`. Move only the Stage G preflight portion of topic review before TTS; reuse the existing director plan in Stage F assembly. Persist Stage G envelopes and the human review separately, then derive the scorecard from those records.

**Tech Stack:** Python, dataclasses, argparse, JSON, pathlib, pytest; existing Documentary V2 research, director, assembly, critic, and verification modules.

**Spec:** `docs/superpowers/specs/2026-09-29-documentary-v2-stage-g-canary-design.md` at or after commit `10b5261`.

## Global Constraints

- Work in the current checkout with an exact file allowlist. Preserve all unrelated tracked and untracked changes; never reset, clean, checkout, or overwrite them.
- The accepted F.1.1 MP4 and report are read-only. Stage G never moves or overwrites them.
- Only an explicit `canary=True` resolves `DOCUMENTARY_V2_CANARY`; environment settings alone cannot activate it.
- Stage G never publishes. Reject `publish=True` before execution and pass `publish=False` explicitly at every publishing-capable downstream boundary. Never invoke publisher entry points.
- The Stage G CLI is the only executable entry point. Do not wire `/generate`, production routing, queue, scheduler, or publisher.
- Do not inject scripts, claims, assets, EDL decisions, or evidence into real canaries. Do not silently fall back to legacy stock.
- Every attempted job leaves EDL, manifest, trace, attribution, and human-review files even when the MP4 is absent. Missing content is `NOT_PRODUCED`; no fabricated provenance or human findings.
- Human review starts as `NOT_RUN`. A pending review or manual production intervention cannot count as autonomous acceptance evidence.
- `CANARY_PASS` requires at least three autonomous accepted jobs in three distinct story types, with more than half rated `GOOD` or `PREMIUM`.
- Out of scope: `main.py`, production pipeline, publishers, queues, schedulers, MIKO, AIRouter, Bonsai, local generation, and analytics implementation.

## Review Focus

- Malformed or duplicate suite entries must fail before research; Task 3 tests path-safe IDs, unique story types, and five-category schema.
- A downstream function unexpectedly gaining publishing capability must be detected before execution; Task 2 tests explicit publish arguments and boundary rejection.
- A failed job with a truncated or unreadable Stage F JSON artifact must still leave a truthful Stage G diagnostic envelope; Task 3 tests this.
- A partly completed human review must remain pending; Task 4 tests missing decision, quality, and intervention fields.
- Multiple failures in one job and the same failure across distinct story types must retain all clusters and trigger the correct aggregate rule; Tasks 4 and 5 test this.

## File map

- `DOCUMENTARY_ENGINE_V2_ACCEPTED_BASELINE.md`: frozen F.1.1 acceptance reference and known limits.
- `video-worker/app/documentary_v2/schemas.py`: canary mode enum only.
- `video-worker/app/documentary_v2/pipeline_mode.py`: explicit-only resolution and diagnostics opt-in.
- `video-worker/app/documentary_v2/review_runner.py`: explicit publish boundary and canary preflight before TTS.
- `video-worker/app/documentary_v2/assembly/orchestrator.py`: explicit `publish=False` boundary; reuse a supplied director plan.
- `video-worker/app/documentary_v2/canary.py`: suite validation, job execution, artifacts, gate classification, human-review reading, clustering, and aggregation. Keep functions small; split this new module only if it becomes too large to review.
- `video-worker/scripts/stage_g_canary.py`: CLI argument validation and calls to the canary module; no publisher import.
- `video-worker/app/documentary_v2/stage_g_suite.json`: five topic/story-type entries with rationale and required dimensions; data, not scripts or assets.
- `video-worker/tests/test_documentary_v2_stage_g.py`: offline contract and failure-path tests.
- `video-worker/video-output/stage_g/<jobid>/`: generated per-job outputs; aggregate report and scorecard at `stage_g/`.

### Task 1: Freeze baseline and add explicit mode

**Files:** Create `DOCUMENTARY_ENGINE_V2_ACCEPTED_BASELINE.md`; modify `video-worker/app/documentary_v2/schemas.py` and `video-worker/app/documentary_v2/pipeline_mode.py`; test `video-worker/tests/test_documentary_v2_stage_g.py`.

**Interfaces:** `resolve_pipeline_mode(*, documentary_v2: bool | None = None, director: bool | None = None, visual_engine: str | None = None, canary: bool = False) -> PipelineMode`; `pipeline_mode_diagnostics(*, canary: bool = False) -> dict`.

- [ ] **Step 1: Write failing tests.** Assert `resolve_pipeline_mode(canary=True)` returns `DOCUMENTARY_V2_CANARY`; omitted or false canary preserves existing legacy results under both V2 and canary-looking environment variables. Assert normal diagnostics do not mention canary, while explicit diagnostics do.
- [ ] **Step 2: Run red tests.** From `video-worker/`: `pytest -q tests/test_documentary_v2_stage_g.py -k mode`; expect the new enum/mode assertions to fail.
- [ ] **Step 3: Add only the enum member and explicit branch.** Put the canary branch before env-backed legacy resolution; do not change `V2_EXECUTION_ACTIVE` or production callers. Record accepted job `sf1120260928-185746_d79a71`, its named MP4, acceptance decision/date, focused tests, no claimed full-suite pass, LOW issues, and Stage G regression invariants in the baseline file.
- [ ] **Step 4: Run green tests and existing mode tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k mode tests/test_documentary_v2_stage_a.py`; expect both to pass.
- [ ] **Step 5: Commit only Task 1 files**, after checking the staged name list.

### Task 2: Enforce publishing boundary and run Stage G preflight before TTS

**Files:** Modify `video-worker/app/documentary_v2/review_runner.py` and `video-worker/app/documentary_v2/assembly/orchestrator.py`; test `video-worker/tests/test_documentary_v2_stage_g.py`.

**Interfaces:** `run_topic_review(topic: str, media_dir: str | Path, *, job_id: str | None = None, max_job_elapsed_sec: float = 360.0, publish: bool = False, canary_preflight: bool = False) -> StageFResult`; `run_stage_f_pipeline(..., publish: bool = False, director_plan: DocumentaryDirectorPlan | None = None) -> StageFResult`. Keep other Stage F parameters and defaults intact.

- [ ] **Step 1: Write failing tests.** `publish=True` raises before research/TTS/director/render in both functions; a mocked Stage F call receives `publish=False` even when environment/config suggests publishing; a required downstream path that cannot guarantee non-publishing fails before execution; mocked publisher entry points are never called; existing non-canary topic-review behavior remains unchanged.
- [ ] **Step 2: Run red tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'publish or preflight'`; expect failures at missing parameters or premature TTS.
- [ ] **Step 3: Add `publish` guards.** Reject true immediately in both functions, pass false explicitly from topic review to Stage F, and keep `StageFResult.publish=False`. Do not add publisher imports or change the existing review CLI.
- [ ] **Step 4: Add the `canary_preflight` branch inside topic review.** After `prepare_review_story` and `plan_beats`, before TTS, record fact/source gate results and run the existing director acquisition/verification with the same job ID, isolated work directory, and bounded `DirectorBudget`. Reject unsupported central claims, absent source evidence, or selection that can support the story only through generic filler; record reason/code, source assessment, visual assessment, budget stop reason, and `FAILED_AT=preflight`. Pass a viable `director_plan` into Stage F so retrieval is not repeated. No scripted or selected-asset injection is permitted. Preserve the non-canary path order.
- [ ] **Step 5: Test preflight failure and reuse.** Assert no TTS or render on source/visual rejection; assert successful preflight passes the same director plan to Stage F and the review runner still enforces the deadline. Run `pytest -q tests/test_documentary_v2_stage_g.py -k 'publish or preflight'` and focused topic-review tests; expect PASS.
- [ ] **Step 6: Commit only Task 2 files and their tests**, after checking the staged name list.

### Task 3: Validate suite and always write the Stage G job package

**Files:** Create `video-worker/app/documentary_v2/canary.py`, `video-worker/app/documentary_v2/stage_g_suite.json`; test `video-worker/tests/test_documentary_v2_stage_g.py`.

**Interfaces:** `load_suite(path: Path) -> list[dict]`; `run_canary_job(entry: dict, output_root: Path, *, job_id: str, max_job_elapsed_sec: float, publish: bool = False) -> dict`; `write_stage_g_package(job_dir: Path, job_id: str, result: StageFResult | None, *, failed_at: str | None, error: str | None, gates: dict, clusters: list[str]) -> dict[str, Path]`.

- [ ] **Step 1: Write failing tests.** Reject missing topic/story type/rationale, duplicate category, unsafe job ID, and `publish=True` before the job starts. Assert each of the five categories exists in the suite and that mocked `run_topic_review` receives `publish=False` even with publish-looking environment/config values. Assert early preflight, downstream exception, and late render failure each leave the five required non-MP4 files with `NOT_PRODUCED`, `FAILED_AT`, error, known gates, and cluster fields; MP4 exists only when produced.
- [ ] **Step 2: Run red tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'suite or package or job'`; expect missing implementation failures.
- [ ] **Step 3: Implement suite and runner.** Assign one path-safe ID per job and directory `video-worker/video-output/stage_g/<jobid>/`; call `resolve_pipeline_mode(canary=True)` and `run_topic_review(..., publish=False, canary_preflight=True)` with the job budget. Catch failures at the Stage G boundary and write the package in a `finally` path. Never call legacy or publisher code.
- [ ] **Step 4: Implement artifact normalization.** For EDL, manifest, trace, and attribution, parse available Stage F JSON and wrap it with Stage G job ID, source path, `artifact_status: PRODUCED`, and original data. For missing or unreadable input, use `artifact_status: NOT_PRODUCED`, `data: null`, the failed stage, error, known gates, and clusters. Rename a produced MP4 only within its new job directory. Do not synthesize provenance, license, EDL decisions, verification, or human findings. Create the review template with `Decision: NOT_RUN` even when no MP4 exists.
- [ ] **Step 5: Run green tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'suite or package or job'`; expect PASS. Include a corrupted JSON test that keeps a diagnostic envelope and marks the job failed.
- [ ] **Step 6: Commit only Task 3 files and tests**, after checking the staged name list.

### Task 4: Implement fail-closed gates, clustering, and human-review contract

**Files:** Modify `video-worker/app/documentary_v2/canary.py`; test `video-worker/tests/test_documentary_v2_stage_g.py`.

**Interfaces:** `classify_failures(codes: list[str]) -> tuple[str, list[str]]`; `read_human_review(path: Path) -> dict`; `evaluate_canary_job(package: dict, review: dict) -> dict`.

- [ ] **Step 1: Write failing table-driven tests.** Cover every normative code-to-cluster group and an unmapped code; assert all applicable clusters are retained and primary selection follows category priority then lexicographic tie-break. Test two clusters from one job without dropping either.
- [ ] **Step 2: Write failing gate/review tests.** Wrong or uncertain entity, evidence misrepresentation, missing provenance/source URL, uncovered important beat, early visual/caption end, frozen tail, dominant slideshow, unavailable/rate-limited/non-pixel VLM, unresolved HIGH issue, and incomplete review must not become automatic PASS. A human review with missing required fields remains pending. Human approval or rerun alone is not manual intervention; final script/asset/shot/EDL/evidence injection is.
- [ ] **Step 3: Run red tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'cluster or gate or human or manual'`; expect failures.
- [ ] **Step 4: Implement mapping and job evaluation.** Use the spec's exact error-code table and primary priority. Preserve unknowns as `UNCLASSIFIED`. Read the human review from the real `.md` file, with `Decision`, quality, timestamped findings, dimensions, and intervention declaration; never derive it from critic output. Keep quality and diagnostics for an intervened job but force `counts_as_autonomous_evidence=false`.
- [ ] **Step 5: Run green tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'cluster or gate or human or manual'`; expect PASS.
- [ ] **Step 6: Commit only Task 4 files and tests**, after checking the staged name list.

### Task 5: Finalize the scorecard and explicit CLI

**Files:** Modify `video-worker/app/documentary_v2/canary.py`; create `video-worker/scripts/stage_g_canary.py`; test `video-worker/tests/test_documentary_v2_stage_g.py`.

**Interfaces:** `build_scorecard(jobs: list[dict], *, test_set_exhausted: bool) -> dict`; `write_aggregate(scorecard: dict, output_root: Path) -> tuple[Path, Path]`; `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing aggregate tests.** Three human-accepted autonomous jobs of three story types, two or more `GOOD/PREMIUM`, and no hard-fail evidence yield `CANARY_PASS`; three of one type, pending review, or manually intervened third job cannot PASS. `ACCEPTABLE`/`WEAK` do not enter the quality numerator. Test PARTIAL with one accepted job and with pending review; test FAIL with zero autonomous success plus a completed creative failure, a repeated hard-failure cluster across two story types, a safety-boundary defect, and exhausted real test set with no autonomous completion. Assert FAIL precedence over PARTIAL.
- [ ] **Step 2: Write failing output/CLI tests.** Scorecard has each named quality dimension, counts, averages, VLM/cost/telemetry fields, intervention fields, failure clusters, and generalization matrix booleans, with no composite score. Missing telemetry is null/unavailable. CLI rejects `--publish` before executing jobs and does not import publisher modules. Aggregate outputs have exact Stage G report/scorecard filenames.
- [ ] **Step 3: Run red tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'scorecard or decision or cli'`; expect failures.
- [ ] **Step 4: Implement aggregation and CLI.** Apply `CANARY_PASS` first, then FAIL predicates, then PARTIAL predicates; keep an unfinished suite as draft `PENDING` rather than success. Count unique story types only across autonomous accepted jobs. Treat `VLM_RATE_LIMIT` separately from creative/safety clusters. CLI uses suite data, job budget, output root, and optional aggregate-only refresh after a human edits review files; it never enables production.
- [ ] **Step 5: Run green tests.** `pytest -q tests/test_documentary_v2_stage_g.py -k 'scorecard or decision or cli'`; expect PASS.
- [ ] **Step 6: Commit only Task 5 files and tests**, after checking the staged name list.

### Task 6: Focused regression and handoff

**Files:** No implementation changes planned; test only if a concrete regression requires a fix within the allowlist.

**Interfaces:** Stage G suite and accepted F.1.1/topic-review regression tests.

- [ ] **Step 1: Run all Stage G tests.** From `video-worker/`: `pytest -q tests/test_documentary_v2_stage_g.py`; record the exact final result.
- [ ] **Step 2: Run focused existing regressions.** `pytest -q tests/test_documentary_v2_stage_a.py tests/test_documentary_v2_stage_f.py tests/test_documentary_v2_stage_f1.py`; include any separate topic-review test module present at execution time. Report failures or interruptions exactly.
- [ ] **Step 3: Check boundaries.** Review the full diff for forbidden files/imports, `publish=False` propagation, Stage F.1.1 baseline immutability, no legacy fallback, exact artifact filenames, and only named files staged. Run `git diff --check` and inspect the final changed-file list.
- [ ] **Step 4: Attempt broader repository tests where practical.** Record any timeout, provider/OAuth/network limitation, or unrelated failure; do not claim an unobserved full-suite pass.
- [ ] **Step 5: Report implementation commits, every changed file, test evidence, five job outcomes, human-review status, and aggregate decision.** Do not run real paid/provider canaries or claim `CANARY_PASS` until the configured five-topic run and human MP4 reviews actually occur.
