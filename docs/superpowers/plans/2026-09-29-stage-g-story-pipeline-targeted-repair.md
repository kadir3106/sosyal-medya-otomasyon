# Stage G Story Pipeline Targeted Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The primary agent implements alone in the current checkout; any subagent is read-only review only.

**Goal:** Make Stage G claim/evidence failures fully diagnosable and repair only the shared research-to-verified-story defects, then rerun the unchanged five-topic suite without publication.

**Architecture:** Preserve the current `generate_script → refine_script → extract_claims → verify_claims → review_runner → canary` route. Add a claim-level audit record at the verifier/story boundary, keep it in failed outputs even on exceptions, and tighten topic/entity relevance, claim strength, and same-subject replacement in that shared route. Keep existing fact gates fail-closed; no media or production routing changes.

**Tech Stack:** Python, pytest, existing `requests`/Wikipedia verification path and Stage G CLI. No new provider or dependency by default.

**Spec:** User-authored attached brief, `C:\Users\Victus\.codex\attachments\cff68419-96ab-4ec3-8248-f8eb82a125c5\Yapıştırılan metin.txt`; diagnosis: `STAGE_G_STORY_FAILURE_ROOT_CAUSE_REPORT.md`.

## Global constraints

- Work in the current dirty checkout. At each task: exact allowlist → failing test → minimum implementation → targeted test → allowlist diff check. Do not stage or alter unrelated files or F.1.1 baseline.
- Do not touch Shot Director, visual retrieval, VisualVerifier, motion graphics, EDL, captions, FFmpeg, MIKO, AIRouter architecture, local generation, publisher, production router, or the five topics.
- `publish=False`; no global V2 enablement. Fail closed on missing or weak evidence, unavailable research, and unsupported central/HIGH claims. Never fabricate source text, provenance, or a safe replacement.
- No new canary until AIRouter health and targeted tests pass. Preserve attempt-1 and attempt-2 artifacts, use new IDs and explicit attempt-3 lineage. Stop after five attempts and aggregate package; no video-stage repair.
- A passing story gate is not a canary PASS. Actual MP4s still require human review; `NOT_RUN` is not acceptance.

## Review focus

- Exception before `PreparedStory` returns must still persist the exact HIGH claim, considered evidence or `MISSING`, rejection reason, and failure code (Task 1 test).
- A matching semantic domain with a different named subject (LEGO versus Hans Wilsdorf/Rolex) must not be a replacement (Task 3 test).
- Sentence-initial `It`/`Today` and generic unit pages must not become claim-supporting entities (Task 2 test).
- A weak/qualified source cannot justify an absolute, exclusive, causal, or stronger ownership claim (Task 3 test).
- A safer supported formulation must be allowed without turning an unsupported sensational version into a topic-level rejection (Task 4 test).

---

### Task 1: Persist a complete claim/evidence failure trace before story behavior changes

**Allowlist:** `video-worker/app/fact_verify.py`, `video-worker/app/documentary_v2/review_story.py`, `video-worker/app/documentary_v2/review_runner.py`, `video-worker/tests/test_documentary_v2_stage_g.py`, `video-worker/tests/test_stage_g_story_repair.py`.

**Interfaces:** Extend existing `VerificationResult`/`PreparedStory` compatibly with defaulted audit data. Define one structured HIGH-claim failure carrying claim trace and failure code to `review_runner`; no bare ID-only exception. Keep source IDs, URL, authority label when known, considered snippet, per-source decision/reason, final status, central flag, replacement attempt/candidates/result, and explicit `MISSING` values. Never log secrets. Save an audit for every verified claim in topic-review metrics/trace, including early failure.

- [ ] Add failing `test_high_claim_failure_persists_full_trace`, `test_unknown_claim_trace_marks_missing_evidence`, and `test_missing_source_url_is_explicit` in `tests/test_stage_g_story_repair.py`; assert saved topic-review JSON metrics as well as the in-memory result.
- [ ] From `video-worker/`, run `pytest -q tests/test_stage_g_story_repair.py -k 'trace or source_url'`; record the expected failure, not an import/setup error.
- [ ] Add the smallest audit carrier at the existing verifier/story boundary and persist it in `review_runner` before early return or catch. Do not change acceptance decisions yet.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py tests/test_documentary_v2_stage_g.py`; inspect only the allowlisted diff and verify no earlier artifact changed.

### Task 2: Relevance and authority at the existing retrieval boundary

**Allowlist:** `video-worker/app/fact_verify.py`, `video-worker/app/script_claims.py`, `video-worker/tests/test_stage_g_story_repair.py`.

**Interfaces:** Give each considered source exactly one of `RELEVANT_PRIMARY`, `RELEVANT_HIGH_QUALITY_SECONDARY`, `WEAK_SECONDARY`, `OFF_TOPIC`, `UNUSABLE`, with explicit reason. Keep Wikipedia as secondary and mark primary `MISSING` when none was retrieved; do not impersonate a primary source. Use topic/claim entity identity and process keywords before scoring claim text; discard sentence-initial pronouns and generic units as source entities. Record rejected hits, not just accepted URLs. No new provider or silent fallback.

- [ ] Add failing `test_off_topic_named_entity_cannot_support_central_claim`, `test_sentence_starter_and_unit_are_not_source_entities`, and `test_source_authority_and_rejection_are_logged`; assert all five relevance values are representable, but do not fabricate primary authority.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py -k 'off_topic or sentence_starter or source_authority'` red; then make the minimum query/filter changes in the existing verifier and claim-entity extractor.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py tests/test_script_quality.py tests/test_documentary_v2_stage_g.py`; inspect allowlisted diff.

### Task 3: Exact-claim support, safe weakening, and same-subject replacement

**Allowlist:** `video-worker/app/fact_verify.py`, `video-worker/app/script_quality.py`, `video-worker/app/story_domains.py`, `video-worker/tests/test_script_quality.py`, `video-worker/tests/test_stage_g_story_repair.py`.

**Interfaces:** Record one entailment decision per considered source: `EVIDENCE_SUPPORTS_EXACT_CLAIM`, `EVIDENCE_SUPPORTS_WEAKER_VERSION`, or `EVIDENCE_DOES_NOT_SUPPORT`. A weaker version must be derived from retrieved evidence text, keep the original narrative domain/subject, and be re-extracted/re-verified; otherwise fail closed. `ReplacementIntent` must include actual topic/claim entities; replacement candidates must pass both semantic-domain and named-subject/beat-relevance checks. Store replacement lineage, including rejected candidates and why.

- [ ] Add failing `test_weak_evidence_does_not_entail_strong_claim`, `test_supported_weaker_sentence_is_reverified`, `test_same_domain_other_subject_replacement_rejected`, `test_supported_same_subject_replacement_keeps_lineage`, and `test_missing_replacement_fails_closed`.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py -k 'weak_evidence or weaker_sentence or replacement'` red; implement minimum shared guards using current verifier/refiner interfaces. Do not add an unverified LLM judgment or a new source provider.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py tests/test_script_quality.py tests/test_documentary_v2_stage_g.py`; inspect allowlisted diff and confirm gates were not relaxed.

### Task 4: Explicit centrality and conservative topic viability

**Allowlist:** `video-worker/app/documentary_v2/review_story.py`, `video-worker/app/documentary_v2/review_runner.py`, `video-worker/app/script_claims.py`, `video-worker/tests/test_stage_g_story_repair.py`.

**Interfaces:** Set `central_claim` explicitly and narrowly: removing it must materially collapse the topic's verifiable narrative; supporting facts are not central by default. Preserve HIGH risk independently of centrality. A preliminary source/subject viability check may reject with `TOPIC_PREFLIGHT_REJECT` only when the topic has no defensible core after a safer same-domain formulation is considered. Record the check and its evidence. Keep the existing all-factual-claims fail-closed final gate unless a separately approved design changes it.

- [ ] Add failing `test_supporting_claim_is_not_central`, `test_unresolved_central_or_high_claim_fails_closed`, `test_verifiable_safer_topic_survives_preflight`, and `test_unviable_topic_rejected_before_script`.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py -k 'central or preflight'` red; implement narrow designation and preflight checks without changing topic strings or weakening verification.
- [ ] Run `pytest -q tests/test_stage_g_story_repair.py tests/test_documentary_v2_stage_g.py tests/test_script_quality.py`; inspect allowlisted diff.

### Task 5: Integration verification and rerun gate

**Allowlist:** tests only if a new regression is exposed; no D.1, media, router, or publisher changes.

- [ ] Run `pytest -q tests/test_stage_g_story_repair.py tests/test_script_quality.py tests/test_documentary_v2_stage_g.py` and then `pytest -q tests/test_documentary_v2_stage_a.py tests/test_documentary_v2_stage_b.py tests/test_documentary_v2_stage_c.py tests/test_documentary_v2_stage_d.py tests/test_documentary_v2_stage_d1.py tests/test_documentary_v2_stage_e.py tests/test_documentary_v2_stage_f.py tests/test_documentary_v2_stage_f1.py tests/test_documentary_v2_stage_g.py`; record results exactly. Compare with prior 43-pass Stage G and 123-pass focused baselines without falsely claiming identical selections. Keep known D.1 separate. Do not claim full-suite PASS unless the full suite completes.
- [ ] Inspect effective AIRouter endpoint and approved model alias without printing secrets; require listener, `GET /v1/models`, and one minimal chat completion smoke test to pass. If not, stop before canaries and report infrastructure blocker.
- [ ] Confirm suite file SHA-256 and five topic strings match the existing suite; record generation-1/2 IDs, establish new generation-3 IDs and lineage. Do not overwrite old directories.

### Task 6: Five unchanged canaries and honest aggregate package

**Allowlist:** new `video-worker/video-output/stage_g/<new-job-id>/` directories, Stage G aggregate files, `STAGE_G_STORY_PIPELINE_REPAIR_REPORT.md`; no old job directory modifications except explicit additive lineage metadata if required.

- [ ] Snapshot the current aggregate report and scorecard to new generation-2-named files before invoking the CLI, because `scripts/stage_g_canary.py` rewrites those aggregate filenames. From `video-worker/`, run `python scripts/stage_g_canary.py --suite app/documentary_v2/stage_g_suite.json --output-root video-output/stage_g --max-job-elapsed-sec 360` (no `--publish`). The script generates five new IDs. Record each job's source/research, story, visual, render, MP4, and human-review states. If a later stage fails, record it and continue; do not fix video code. If text gateway fails, stop.
- [ ] Preserve prior generations, add exact lineage, and build a scorecard whose current decision is based on generation 3 while prior attempts remain auditable. Never turn pending human review into PASS.
- [ ] Write `STAGE_G_STORY_PIPELINE_REPAIR_REPORT.md` with every required field, per-job comparison, tests, files changed, and explicit `NOT_RUN`/`MISSING` where applicable. Inspect artifact completeness, five topics, no fabricated evidence, no publish/global V2 change, and final diff. Stop.

## Plan review checkpoint

The user already chose single-implementer inline execution and the existing dirty checkout. Review this plan before implementation; after approval, execute tasks in order and do not delegate writes.
