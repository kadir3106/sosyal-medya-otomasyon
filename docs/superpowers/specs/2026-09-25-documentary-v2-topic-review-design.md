# Documentary Engine V2: Topic-to-Review MP4 Design

**Date:** 2026-09-25
**Status:** Conversational design approved; written specification awaiting user review

## Purpose and success

The user supplies a topic. The system researches and drafts a short mini-documentary, chooses relevant visual material, assembles a real MP4, and returns an evidence-bearing review package. The user must not have to write each video's script. This first increment ends at human review: it does not schedule, send to Telegram, publish, or enable V2 as the production default.

Success means more than an FFmpeg exit code. The package must let a reviewer judge claim support, shot-to-beat fit, native motion versus photo/zoom dependence, repeated assets, generic filler, captions, hook/payoff, pacing, sound balance, and mini-documentary coherence. Automated checks may flag these properties but cannot replace the human verdict.

## Scope and boundaries

- Add one explicit, review-only topic entry point. Do not route `/generate`, the daily scheduler, Telegram approval, or publishers through V2 in this increment.
- Reuse existing script generation, script-quality checks, TTS, subtitles, Stage B-D acquisition/verification/direction, Stage E recovery, and Stage F EDL/render/critic where valid. Do not redesign AIRouter, MİKO, providers, or publishers.
- Remove topic-specific Rolex/Wilsdorf/watch assumptions from shared fact verification, beat planning, query construction, recovery, and repair paths touched by this flow. Preserve the Rolex example only as a fixture or test.
- Never turn an unavailable verifier, absent source, failed critic, unknown license, or uncovered important beat into a PASS by default.
- Keep real/entity and archive footage distinct from stock, stills, motion graphics, synthetic footage, and camera movement added to a still. Zoom does not count as native motion.
- No new dependency or model abstraction unless an existing facility cannot satisfy a concrete requirement.

## Chosen approach

Build a narrow vertical slice using an explicit V2 review command. This isolates new behavior from production and allows cross-topic evaluation. Direct integration into daily generation/Telegram is deferred until the review slice earns trust; a wholesale engine rewrite would duplicate working acquisition, render, and telemetry code.

## Components and data flow

1. **Story preparation.** Given a nonempty topic, use the current script generator and script-quality pipeline. Re-check factual claims against the *final* spoken script after edits, not just the first draft. Evidence records must retain claim ID, status, source URL/title/provider, and any uncertainty. The source lookup must be bound to that claim's topic/entities; an unrelated cached page is not supporting evidence. Unsupported or unknown high-risk claims stop before narration unless removed or softened and then re-verified. Lower-risk uncertainty may yield a labeled REVIEW_REQUIRED artifact; it never produces fact PASS merely because a claim object exists.
2. **Beat planning.** Convert the final script to ordered `StoryBeat` objects with exact spoken spans, narrative role, entities, semantic domain, visual purpose, motion/evidence/authenticity requirements, and only the claim IDs relevant to each beat. Use the existing text-model route for structured planning, validate its output deterministically against the final script and claim set, and reject invented entities/events. If structured planning fails, a conservative sentence-based fallback may make a review artifact, but its uncertainty remains visible and cannot yield story/coverage PASS.
3. **Visual direction.** Feed those beats to existing Stage D. Search queries derive from the actual beat entities and concepts, never fixed watch or ownership vocabulary. Candidate pixels/video frames are verified before selection. Important beats without authentic relevant media may use evidence-bound Stage E diagrams or archival stills; they may not be hidden by generic stock or fabricated timeline facts.
4. **Assembly.** Feed selected asset paths, per-asset provenance, TTS word boundaries, captions, and optional curated music to Stage F. Recovery and targeted repair use only facts/events supplied with the current story. Write MP4, EDL, manifest, attribution, critique, and a concise review report under a job-specific output path. No publish side effect is permitted.
5. **Verdict.** Report separately what ran and what did not. PASS requires actually executed checks for facts, story consistency, visual coverage, no-slideshow, license/provenance, technical render, and final video critique. Any uncertain or unavailable mandatory check produces REVIEW_REQUIRED; a demonstrable factual, rights, or technical defect produces FAIL. Even PASS means ready for human review, never approval to publish.

## Failure and resource policy

- Bound whole-job searches, downloads, vision calls, critic calls, and elapsed time, in addition to existing per-shot limits. Record which budget stopped work and why. Cache or reuse a candidate's visual verification within the job rather than paying twice for the same content.
- Groq 429/timeout must terminate that verification attempt promptly; no unbounded retry or silent zero-call PASS. A review MP4 may still be produced from previously verified assets, labeled REVIEW_REQUIRED.
- Unknown rights yield REVIEW_REQUIRED; known restricted rights block use and yield FAIL. Store the original provider URL, license, creator, and attribution requirement with each selected asset; never infer a reusable license solely from a source name.
- If a required asset or narration/caption input is missing, return a failed review package with diagnostics instead of a misleading partial PASS or publishing fallback.
- Preserve temporary and existing output files unless the code's normal, job-scoped cleanup is proven safe; unrelated worktree changes are out of scope.

## Acceptance and evidence

- Deterministic offline tests cover Rolex, the Aral Sea, and the Panama Canal. None may inherit another topic's entities, domains, search terms, evidence, or timeline events.
- Tests pin claim-to-source and claim-to-beat joins; a source from another entity cannot support a claim. Unsupported/unknown claims, a failed planner, Groq rate limiting, critic outage, uncovered important beat, and unknown license must not report PASS.
- EDL tests confirm ordered beat coverage, distinct source versus visual-information counts, asset reuse limits, native-motion accounting, and captions aligned to speech. Technical checks verify playable video/audio streams and duration.
- One bounded live smoke run, when credentials and provider quotas permit, yields a real review MP4 plus EDL/manifest/attribution/critique/report. Any skipped remote check is declared, not passed.
- A human evaluates the produced MP4 against the original Stage F concerns: slideshow feel, still+zoom reliance, genuine motion, shot/beat match, motion-graphic quality, filler, reuse, caption obstruction, hook/payoff, rhythm, voice/music balance, and documentary coherence. The acceptance report records PASS, REVIEW_REQUIRED, or FAIL with beat-local corrections only.

## Existing-code findings behind this design

- `video-worker/app/pipeline.py` already has topic-to-script, script quality, TTS, captions, music profiles, and legacy review notification, but it does not call Stage F.
- `video-worker/app/documentary_v2/pipeline_mode.py` leaves V2 execution inactive by default.
- `video-worker/app/documentary_v2/assembly/orchestrator.py` has Rolex-specific beat/recovery/repair defaults and placeholder quality PASS values; `director/query_compiler.py` contains a watch-specific query.
- `video-worker/app/fact_verify.py` seeds and falls back to Rolex/Wilsdorf evidence even for unrelated topics. `script_quality.py` currently retains decisions but not all source-bearing verification results needed for final-claim provenance.
- The existing Stage F test suite largely uses Rolex fixtures; cross-topic behavior remains unproven.

## External constraints checked

- Pexels does not provide rich photo titles/tags/metadata through its API, so search metadata alone cannot establish visual relevance: https://help.pexels.com/hc/en-us/articles/47677748516121-Are-media-details-and-statistics-available-through-the-API
- Groq vision images consume tokens and have per-request image limits; actual account limits and 429 responses must be respected: https://console.groq.com/docs/vision and https://console.groq.com/docs/rate-limits
- Wikimedia files carry file-specific reuse conditions; provenance must preserve the file's terms and attribution: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
