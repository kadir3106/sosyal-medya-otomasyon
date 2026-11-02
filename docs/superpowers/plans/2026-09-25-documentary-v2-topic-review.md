# Documentary V2 Topic-to-Review MP4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a topic, produce an evidence-bearing, unpublished Documentary Engine V2 review MP4 without hand-writing each script.

**Architecture:** Add an explicit review-only runner that reuses script generation, fact checks, TTS, subtitles, Stage D selection, and Stage F assembly. Remove domain-specific defaults from the shared paths it calls, carry real evidence/provenance into gates, and fail closed when a mandatory check cannot run. The legacy `/generate` and publish paths stay untouched.

**Tech Stack:** Python 3, pytest, existing OpenAI-compatible text route, Direct Groq vision, existing providers, FFmpeg.

**Spec:** `docs/superpowers/specs/2026-09-25-documentary-v2-topic-review-design.md`

## Global Constraints

- Add one explicit, review-only topic entry point. Do not route `/generate`, the daily scheduler, Telegram approval, or publishers through V2 in this increment.
- Reuse existing script generation, script-quality checks, TTS, subtitles, Stage B-D acquisition/verification/direction, Stage E recovery, and Stage F EDL/render/critic where valid. Do not redesign AIRouter, MİKO, providers, or publishers.
- Never turn an unavailable verifier, absent source, failed critic, unknown license, or uncovered important beat into a PASS by default.
- Zoom does not count as native motion.
- No new dependency or model abstraction unless an existing facility cannot satisfy a concrete requirement.
- The repo has extensive pre-existing changes: do not reset, clean, or stage unrelated files; every commit stages only the task's named paths. `video-worker/app/documentary_v2/` and several tests are currently untracked, so inspect the exact staged diff before each commit.

## Review Focus

1. A non-luxury topic inherits a Rolex/wealth prompt or Wikipedia source: Task 1 and Task 2 cross-topic tests must catch it.
2. The final script differs from the initially verified draft: Task 2 must re-extract/re-verify final spoken claims and block unresolved high-risk facts.
3. A beat planner changes punctuation, drops narration, or invents a named entity: Task 3 must reject it and label its conservative fallback REVIEW_REQUIRED.
4. Groq 429, a missing critic, an unvalidated beat-plan fallback, or exhausted search/VLM budget: Task 3/4/5/6 must finish boundedly and never report PASS.
5. A selected asset has unknown/restricted rights, or a still is counted as genuine motion: Task 4/5/6 must preserve provenance, block known restrictions, and retain a review flag for unknown rights or slideshow dependence.

---

## File map

- `video-worker/app/script_gen.py`: opt-in documentary-review prompt; legacy prompt remains default.
- `video-worker/app/fact_verify.py`: topic/entity-bound evidence lookup; no Rolex fallback for unrelated topics.
- `video-worker/app/documentary_v2/review_story.py` (new): final-script verification and `VerifiedStory`/`VerifiedClaim` adapter.
- `video-worker/app/documentary_v2/beat_planner.py` (new): structured beat output with exact-span and claim/entity validation.
- `video-worker/app/documentary_v2/schemas.py`, `director/shot_director.py`, `director/query_compiler.py`: explicit generic visual purpose and topic-specific search terms.
- `video-worker/app/documentary_v2/director/pipeline.py`: whole-job limits and selected-asset provenance.
- `video-worker/app/documentary_v2/assembly/orchestrator.py`, `assembly/edl_render.py`: story facts in recovery/repair, real gate states, and a bounded FFmpeg call.
- `video-worker/app/documentary_v2/review_runner.py` (new), `video-worker/scripts/documentary_v2_review.py` (new): isolated topic entry, TTS/captions/music, Stage F invocation, report.
- Focused tests go in `video-worker/tests/test_documentary_v2_topic_review.py`; existing Stage A-F/legacy tests remain regression checks.

### Task 1: Opt-in topic-neutral documentary script

**Files:** Modify `video-worker/app/script_gen.py:56-224`; test `video-worker/tests/test_documentary_v2_topic_review.py`.

**Interfaces:** `generate_script(topic: str, api_key: str, lang: str = "en", winning_context: str | None = None, *, style: str = "legacy") -> dict`. Existing callers keep the same behavior. `style="documentary_review"` returns the existing required keys plus `hook_selected`, but does not run luxury-oriented query normalization or ownership-chart hook fallbacks.

- [ ] **Step 1: Write the failing test.**

```python
def test_documentary_script_prompt_has_no_luxury_bias(monkeypatch):
    from app import script_gen
    seen = []
    def fake_llm(messages, api_key):
        seen.append(messages[0]["content"])
        return ('{"script":"The Aral Sea shrank after river diversion.","title":"The Aral Sea","description":"A shrinking sea.","tags":["history"]}', "fixture")
    monkeypatch.setattr(script_gen, "_call_llm_with_fallback", fake_llm)
    data = script_gen.generate_script("Aral Sea", "fixture", style="documentary_review")
    assert data["script"].startswith("The Aral Sea")
    assert "Rolex" not in seen[0] and "Luxury Lifestyle" not in seen[0]
    assert "scene_stock_queries" not in data
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py::test_documentary_script_prompt_has_no_luxury_bias -q`. Expected: FAIL because `style` is not accepted.
- [ ] **Step 3: Implement the minimal branch.** Keep current `PROMPT_TEMPLATE` and post-processing unchanged for `legacy`. Add a `DOCUMENTARY_REVIEW_PROMPT` that asks for a 22-38s evidence-conscious mini-documentary with a concrete hook, development, payoff, no invented sources, and the existing JSON required keys. At the top of `generate_script`, use:

```python
if style not in {"legacy", "documentary_review"}:
    raise ValueError(f"unknown script style: {style}")
if style == "documentary_review":
    content, _ = _call_llm_with_fallback(
        [{"role": "user", "content": DOCUMENTARY_REVIEW_PROMPT.format(topic=topic)}], api_key
    )
    data = _parse(content)
    _validate_script_shape(data)
    data["hook_selected"] = re.split(r"(?<=[.!?])\s+", data["script"].strip())[0]
    return data
```

- [ ] **Step 4: Run** the new test and `python -m pytest tests/test_pipeline.py tests/test_script_quality.py -q`. Expected: PASS, including legacy compatibility.
- [ ] **Step 5: Stage only `video-worker/app/script_gen.py` and the new test file; inspect `git diff --cached --check` and commit `feat: add opt-in documentary script style`.**

### Task 2: Topic-bound evidence and exact-final-script story preparation

**Files:** Modify `video-worker/app/fact_verify.py:37-154`; create `video-worker/app/documentary_v2/review_story.py`; test `video-worker/tests/test_documentary_v2_topic_review.py`.

**Interfaces:** `prepare_review_story(topic: str, api_key: str, *, verifier: FactVerificationProvider | None = None) -> PreparedStory`. `PreparedStory` contains `story: VerifiedStory`, `claims: list[VerifiedClaim]`, `title: str`, `gates: dict[str, str]`, `reasons: list[str]`. High-risk unsupported/unknown factual claims raise `ValueError` before TTS.

- [ ] **Step 1: Write failing tests** for no Rolex seed/fallback and final-script verification. Use a fake provider whose `_wikipedia_evidence` records titles, then assert no title contains `Rolex` or `Wilsdorf` for topic `Aral Sea`. Monkeypatch `generate_script` and `refine_script` to return a changed final sentence, pass a fake `verifier.verify_claims`, and assert it receives the changed sentence—not the draft. Also assert a HIGH/unknown final claim raises `ValueError`.

```python
def test_aral_fact_lookup_never_seeds_rolex(monkeypatch):
    from app.fact_verify import FactVerificationProvider
    from app.script_claims import ScriptClaim
    provider, titles = FactVerificationProvider(), []
    monkeypatch.setattr(provider, "_wikipedia_evidence", lambda title: titles.append(title) or {})
    monkeypatch.setattr(provider, "_wikipedia_search_extract", lambda query: None)
    claim = ScriptClaim("aral", "The Aral Sea shrank.", "historical", ["Aral Sea"], risk="HIGH", verification_required=True)
    provider.verify_claims([claim], topic="Aral Sea")
    assert not any("rolex" in title.lower() or "wilsdorf" in title.lower() for title in titles)
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py -k 'aral_fact_lookup or final_script' -q`. Expected: FAIL on the Rolex seed and missing adapter.
- [ ] **Step 3: Remove fixed evidence seeds and fallback.** Seed only the supplied topic plus claim entities. `_verify_one` may use cached topic evidence only when the claim has no entities or the topic/entity appears in the claim text; otherwise search the claim entity and leave status unknown if no matching source is found. Never score a claim against an unrelated cached page. In `review_story.py`, re-extract after `refine_script` and call the verifier again:

```python
@dataclass
class PreparedStory:
    story: VerifiedStory
    claims: list[VerifiedClaim]
    title: str
    gates: dict[str, str]
    reasons: list[str]

def prepare_review_story(topic: str, api_key: str, *, verifier=None) -> PreparedStory:
    if not topic.strip():
        raise ValueError("topic is empty")
    verifier = verifier or FactVerificationProvider()
    draft = generate_script(topic, api_key, style="documentary_review")
    quality = refine_script(draft["script"], topic=topic, verifier=verifier)
    final = quality.final_script.strip()
    if not final:
        raise ValueError("verified script is empty")
    factual = [c for c in extract_claims(final, topic=topic) if c.verification_required]
    results = {v.claim_id: v for v in verifier.verify_claims(factual, topic=topic)}
    claims = []
    for c in factual:
        v = results.get(c.claim_id)
        status = v.status if v else "unknown"
        sources = list(v.sources) if v else []
        if c.risk == "HIGH" and (status != "supported" or not sources):
            raise ValueError(f"unresolved high-risk final claim: {c.claim_id}")
        claims.append(VerifiedClaim(c.claim_id, c.text, c.claim_type, c.risk, status, sources))
    gates = {
        "FactQualityGate": "PASS" if factual and all(c.status == "supported" and c.evidence for c in claims) else "REVIEW_REQUIRED",
        "StoryQualityGate": "PASS" if not quality.quality_checks.get("story_flags") and not quality.quality_checks.get("linguistic_issues") else "REVIEW_REQUIRED",
        "StoryConsistencyGate": str(quality.story_consistency.get("status") or "NOT_RUN"),
    }
    story = VerifiedStory(f"story:{topic}", topic, draft["script"], final, hook=quality.hook, claim_ids=[c.claim_id for c in claims])
    return PreparedStory(story, claims, str(draft["title"]), gates, [])
```

- [ ] **Step 4: Run** the new tests plus `python -m pytest tests/test_script_quality.py tests/test_source_diversity.py -q`. Expected: PASS; no regression to existing claim decisions.
- [ ] **Step 5: Stage only the three named paths, inspect staged diff, and commit `fix: bind review-story evidence to final topic claims`.**

### Task 3: Exact, topic-generic beat plan and search intent

**Files:** Create `video-worker/app/documentary_v2/beat_planner.py`; modify `video-worker/app/documentary_v2/schemas.py:336-359`, `director/shot_director.py:39-78`, `director/query_compiler.py:44-85`; test `video-worker/tests/test_documentary_v2_topic_review.py`.

**Interfaces:** `plan_beats(topic: str, script: str, claims: list[VerifiedClaim], api_key: str) -> BeatPlan`; `BeatPlan` has `beats: list[StoryBeat]`, `gate: str`, `reasons: list[str]`. Add `StoryBeat.visual_purpose: str = ""`; `DocumentaryShotDirector` honors it when it is one of the existing shot purposes. Claim IDs are derived from exact spoken spans, never trusted from the model.

- [ ] **Step 1: Write failing tests.** With a mocked text-model response, assert the Aral Sea plan preserves every character of the two-sentence script, attaches only the matching claim, and emits no watch/ownership query. Give the planner a response with an invented `Rolex` entity or a dropped sentence and assert fallback gate `REVIEW_REQUIRED`.

```python
def test_aral_queries_do_not_contain_watch_terms():
    from app.documentary_v2.director.query_compiler import compile_search_intents
    from app.documentary_v2.schemas import ShotRequirement
    req = ShotRequirement("sr:aral", "beat:aral", visual_purpose="SHOW_EVIDENCE", required_entities=["Aral Sea"], required_visual_concept="shrinking shoreline", semantic_domain="environment")
    queries = [x.query.lower() for x in compile_search_intents(req)]
    assert not any("watch" in q or "foundation" in q or "ownership" in q for q in queries)
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py -k 'beat or queries' -q`. Expected: FAIL on fixed ownership/document queries and missing planner.
- [ ] **Step 3: Implement planner and generic direction.** Call existing `_call_llm_with_fallback` with a schema-shaped instruction to return ordered exact `spoken_span`, role, entities, semantic domain, visual purpose, concept, and motion/evidence requirements. Validate text coverage and entity set before constructing beats. The conservative fallback uses punctuation-preserving sentence splits with `semantic_domain="unknown"` and returns `REVIEW_REQUIRED`:

```python
@dataclass
class BeatPlan:
    beats: list[StoryBeat]
    gate: str
    reasons: list[str]

def _exact_spans(script: str, spans: list[str]) -> bool:
    cursor = 0
    for span in spans:
        start = script.find(span, cursor)
        if start < 0 or script[cursor:start].strip():
            return False
        cursor = start + len(span)
    return not script[cursor:].strip()

def _fallback_beats(script: str, claims: list[VerifiedClaim]) -> BeatPlan:
    spans = [s for s in re.split(r"(?<=[.!?])\s+", script.strip()) if s]
    beats = [StoryBeat(beat_id=f"beat:{i}", spoken_span=span, narrative_role="development", semantic_domain="unknown", required_visual_concept=span, claim_ids=[c.claim_id for c in claims if c.text == span], importance="important") for i, span in enumerate(spans)]
    return BeatPlan(beats, "REVIEW_REQUIRED", ["structured_beat_plan_unavailable"])
```

In `shot_director._visual_purpose`, accept a valid explicit `beat.visual_purpose` before heuristics. Replace query compiler's `ownership document`, `foundation charter`, `manufacturing assembly`, and `watch close up` literals with phrases composed from `req.required_visual_concept`, entities, and `req.action`. Do not invent a product or legal relationship.
- [ ] **Step 4: Run** the new tests plus `python -m pytest tests/test_documentary_v2_stage_d.py tests/test_documentary_v2_stage_f.py -q`. Expected: PASS after updating only tests whose old expected query was intentionally domain-specific.
- [ ] **Step 5: Stage only the five named paths, inspect staged diff, and commit `feat: plan evidence-bound beats across topics`.**

### Task 4: Whole-job visual budgets and selected provenance

**Files:** Modify `video-worker/app/documentary_v2/director/pipeline.py:49-350`; test `video-worker/tests/test_documentary_v2_topic_review.py`.

**Interfaces:** Extend `DirectorBudget` with `max_total_searches=12`, `max_total_vlm=12`, `max_total_materializations=12`, `max_elapsed_sec=180.0`. `run_director_plan` records `diagnostics["budget_stop_reason"]` and `diagnostics["selected_provenance"]` keyed by selected asset ID/candidate ID. Existing `verify_candidate(..., use_cache=True)` remains the within-job cache path.

- [ ] **Step 1: Write failing tests** using Stage D `FixtureCandidate`s: a zero total-VLM budget performs zero verifications and records `total_vlm`; a selected candidate retains its exact provider/source/license/creator in `selected_provenance`; `RESTRICTED` candidates are never selected.

```python
def test_director_budget_has_whole_job_limits():
    from app.documentary_v2.director.pipeline import DirectorBudget
    budget = DirectorBudget(max_total_searches=0, max_total_vlm=0, max_total_materializations=0)
    assert budget.max_total_vlm == 0
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py -k 'budget or provenance' -q`. Expected: FAIL because the fields and selected-provenance map do not exist.
- [ ] **Step 3: Add the global counters and guards.** Before each acquisition/materialization/verification, stop when its total limit or the monotonic deadline is reached and record the reason. Before ranking, exclude `LicensePolicy.KNOWN_RESTRICTED` or `LicenseState.RESTRICTED/PROPRIETARY` candidates. When a candidate is selected, store its `provenance.to_dict()` under both `selection.asset_id` and `selection.candidate_id`:

```python
diagnostics.setdefault("selected_provenance", {})[selection.asset_id] = chosen_cand.provenance.to_dict()
diagnostics["selected_provenance"][selection.candidate_id] = chosen_cand.provenance.to_dict()
```

Keep per-shot limits. Do not add a new cache framework; verification already uses its cache when `work_dir` is set.
- [ ] **Step 4: Run** the new tests plus `python -m pytest tests/test_documentary_v2_stage_d.py tests/test_documentary_v2_stage_c.py -q`. Expected: PASS.
- [ ] **Step 5: Stage only the pipeline and test path, inspect staged diff, and commit `feat: bound V2 visual work and retain selected rights`.**

### Task 5: Remove Rolex recovery defaults and make Stage F gates truthful

**Files:** Modify `video-worker/app/documentary_v2/assembly/orchestrator.py:88-460` and `assembly/edl_render.py:38-185`; test `video-worker/tests/test_documentary_v2_topic_review.py` and existing Stage F tests.

**Interfaces:** Add keyword arguments `story_gates: dict[str, str] | None = None`, `beat_plan_gate: str = "NOT_RUN"`, `timeline_events: list[dict] | None = None`, and `critic_frame_budget: int = 3` to `run_stage_f_pipeline`. Preserve existing callers. If no external `provenance_by_asset` is supplied, use `director_plan.diagnostics["selected_provenance"]`. `BeatPlanGate` records the planner status; `FinalVideoQualityGate` is `NOT_RUN` if disabled, never an omitted PASS.

- [ ] **Step 1: Write failing tests.** An Aral Sea script without explicit beats must never create luxury-watch domains or Rolex timeline events. With no `story_gates`, fact/story/consistency gates are `NOT_RUN`; with supplied real statuses, preserve them. `beat_plan_gate="REVIEW_REQUIRED"` yields `BeatPlanGate=REVIEW_REQUIRED`. A critic disabled by config is `NOT_RUN`; unknown license is `REVIEW_REQUIRED`; `RESTRICTED` is `FAIL` and cannot be selected. A review run never sends more than three frames per critic pass. Mock `subprocess.run` to raise `TimeoutExpired` and assert FFmpeg render ends in a failed package rather than hanging.

```python
def test_fallback_beats_are_not_rolex():
    from app.documentary_v2.assembly.orchestrator import _beats_from_script
    beats = _beats_from_script("The Aral Sea shrank. Fishing towns changed.", "Aral Sea")
    assert all("luxury_watch" not in b.semantic_domain for b in beats)
    assert all("Rolex" not in b.primary_entities for b in beats)
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py -k 'fallback_beats or stage_f_gate' -q`. Expected: FAIL on Rolex defaults and placeholder PASS.
- [ ] **Step 3: Replace fixed recovery inputs and gates.** Use only caller-supplied `timeline_events`; default to an empty list. The repair fallback reads the current beat's `semantic_domain` and claim IDs. Make `_beats_from_script` a neutral compatibility fallback marked REVIEW_REQUIRED by absent `beat_plan_gate`. Record `BeatPlanGate=beat_plan_gate`; map supplied `story_gates` verbatim and default each missing mandatory story gate to `NOT_RUN`. Cap each critic pass with `max_frames=critic_frame_budget`, leaving only one Groq batch at the default of three. Compute license status from the attribution manifest, not a provider label:

```python
rights = [str(a.get("license") or "UNKNOWN") for a in attribution]
if any(x in {"RESTRICTED", "PROPRIETARY"} for x in rights):
    result.gates["LicenseProvenanceGate"] = "FAIL"
elif not rights or any(x not in {"INTERNAL", "STOCK_LICENSED", "PUBLIC_DOMAIN", "CC0"} for x in rights):
    result.gates["LicenseProvenanceGate"] = "REVIEW_REQUIRED"
else:
    result.gates["LicenseProvenanceGate"] = "PASS"
```

Keep existing `no_slideshow_gate`: it counts native video seconds, not zoomed stills. A rendered beat does not count as covered if its Stage D coverage status is `PARTIAL` or `UNCOVERED`. Add `render_timeout_sec: float = 240.0` to `render_from_edl` and pass it to `subprocess.run(cmd, capture_output=True, text=True, timeout=render_timeout_sec)`; Stage F catches the timeout as `render_failed`. Preserve Stage F report files and never call publish.
- [ ] **Step 4: Run** new tests plus `python -m pytest tests/test_documentary_v2_stage_f.py tests/test_documentary_v2_stage_e.py -q`. Expected: PASS.
- [ ] **Step 5: Stage only orchestrator, EDL renderer, and the test path, inspect staged diff, and commit `fix: make V2 assembly topic-neutral and gates evidence-based`.**

### Task 6: Explicit topic runner, cross-topic acceptance, and review package

**Files:** Create `video-worker/app/documentary_v2/review_runner.py`, `video-worker/scripts/documentary_v2_review.py`; modify `video-worker/tests/test_documentary_v2_topic_review.py`.

**Interfaces:** `run_topic_review(topic: str, media_dir: str | Path, *, job_id: str | None = None, max_job_elapsed_sec: float = 360.0) -> StageFResult`. CLI: `python scripts/documentary_v2_review.py --topic "Aral Sea" --media-dir PATH`. It invokes only the review path. Result/report include `automated_verdict`, full gate states, evidence/provenance paths, budgets, and the human-review rubric. `PASS` means ready for human inspection, not approved for publication.

- [ ] **Step 1: Write failing tests** with monkeypatched external calls: blank topic fails without TTS; a changed final script is the exact TTS input; runner calls Stage F with `live_acquire=True`, `materialize=True`, prepared beats/claims and real gates; missing audio/caption returns FAIL diagnostics; critic outage and exhausted budgets return REVIEW_REQUIRED; no publisher/Telegram function is called. Parameterize fixture stories for Rolex, Aral Sea, and Panama Canal and assert cross-topic query/evidence isolation.

```python
def test_automated_verdict_requires_every_mandatory_gate():
    from app.documentary_v2.review_runner import automated_verdict
    gates = {name: "PASS" for name in ("FactQualityGate", "StoryQualityGate", "StoryConsistencyGate", "BeatPlanGate", "VisualCoverageGate", "NoSlideshowQualityGate", "LicenseProvenanceGate", "TechnicalRenderQA", "FinalVideoQualityGate")}
    assert automated_verdict(gates) == "PASS"
    gates["FinalVideoQualityGate"] = "NOT_RUN"
    assert automated_verdict(gates) == "REVIEW_REQUIRED"
    gates["LicenseProvenanceGate"] = "FAIL"
    assert automated_verdict(gates) == "FAIL"
```

- [ ] **Step 2: Run:** `cd video-worker; python -m pytest tests/test_documentary_v2_topic_review.py -k 'runner or automated_verdict or cross_topic' -q`. Expected: FAIL because the runner does not exist.
- [ ] **Step 3: Build the runner using existing helpers.** Compose `prepare_review_story`, `plan_beats`, `synthesize_speech`, `write_ass`, `build_music_profile`, `get_or_create_bgm`, and `run_stage_f_pipeline`. Use job-scoped paths under `media_dir`; validate audio and ASS files before assembly. Use `asyncio.run(synthesize_speech(...))` only in the synchronous CLI path. Set `deadline=time.monotonic()+max_job_elapsed_sec`; check it before each blocking stage. Stage D's elapsed-time checks, Direct Groq's request timeout, media-download timeouts, and Task 5's FFmpeg timeout bound in-flight operations. Call Stage F with `beats=beat_plan.beats`, `claims=prepared.claims`, `story_gates=prepared.gates`, `beat_plan_gate=beat_plan.gate`, `run_critic=True`, `live_acquire=True`, `materialize=True`, and a bounded `DirectorBudget`. Report all mandatory gates with this reducer:

```python
MANDATORY_GATES = ("FactQualityGate", "StoryQualityGate", "StoryConsistencyGate", "BeatPlanGate", "VisualCoverageGate", "NoSlideshowQualityGate", "LicenseProvenanceGate", "TechnicalRenderQA", "FinalVideoQualityGate")

def automated_verdict(gates: dict[str, str]) -> str:
    values = [gates.get(name, "NOT_RUN") for name in MANDATORY_GATES]
    if "FAIL" in values:
        return "FAIL"
    if any(value != "PASS" for value in values):
        return "REVIEW_REQUIRED"
    return "PASS"
```

Catch input/research/TTS/render failures into a job-specific JSON+Markdown diagnostic report with `publish=false`, not a legacy fallback. The Markdown report includes a human checklist for slideshow, native motion, shot/beat, graphics, filler/reuse, captions, hook/payoff, rhythm, voice/music, and mini-documentary feel.
- [ ] **Step 4: Run** `python -m pytest tests/test_documentary_v2_topic_review.py tests/test_documentary_v2_stage_a.py tests/test_documentary_v2_stage_b.py tests/test_documentary_v2_stage_c.py tests/test_documentary_v2_stage_d.py tests/test_documentary_v2_stage_e.py tests/test_documentary_v2_stage_f.py tests/test_pipeline.py -q` from `video-worker`. Then run one bounded live smoke with credentials if present; otherwise mark remote checks NOT_RUN and record why. Inspect the resulting MP4 personally before claiming a quality PASS.
- [ ] **Step 5: Stage only the runner, CLI, and test paths; inspect staged diff; commit `feat: produce topic-driven V2 review packages`.** Report the MP4/EDL/manifest/attribution/critic/report paths, automated gate states, and independent human PASS/REVIEW_REQUIRED/FAIL. Do not publish.

## Plan self-review and execution notes

- Every spec component is assigned: topic-neutral script (1), final claim evidence (2), beat/visual intent (3), bounded acquisition and rights (4), assembly/gates (5), isolated runner and three-topic acceptance (6).
- Keep task commits scoped. Because Stage A-F code is presently untracked, a task commit must stage only files it actually reviewed; never include generated video, logs, pending state, or unrelated changes.
- The live smoke may be REVIEW_REQUIRED due to external quotas. An unavailable service is evidence of an outage, not evidence of visual or factual quality.
- The resulting automation is review-only. Human inspection and any beat-local repairs remain required before a later integration project considers Telegram or publishing.
