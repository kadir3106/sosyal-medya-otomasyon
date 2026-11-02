# Documentary Engine V2 — Stage G Post-Infra Rerun

Date: 2026-09-29 (Europe/Istanbul)

**Current aggregate decision: CANARY_FAIL.** This is the existing deterministic Stage G decision for the five post-recovery attempts only. The five original AIRouter-blocked attempts remain historical infrastructure evidence and do not count as creative failures or current generalization evidence.

## Required results

- **AIRouter pre-run health:** **PASS.** `127.0.0.1:20128` listening; authenticated `GET /v1/models` HTTP 200 (81 ms), primary alias `groq/qwen/qwen3.8-27b` present; minimal non-streaming `/v1/chat/completions` request with that alias HTTP 200, non-empty response (319 ms). No key or response text printed.
- **Focused tests:** `tests/test_documentary_v2_stage_g.py`: **43 passed** in 0.57 s. A broader nine-file V2 test run completed with **195 passed, 1 failed, 1 skipped, 34 warnings** in 32.98 s. The failure was `tests/test_documentary_v2_stage_d1.py::test_chat_detects_gateway_drop`: the test patches `app.http_client.session`, whereas `remote_vlm.py` currently creates a separate `requests.Session()`, so the test sent its fixture request to `example.invalid` and failed on DNS resolution. No test or production code was changed in this rerun task. The previous 123-pass result was **not** re-executed as that exact selection and is not claimed as a new result. Full suite: **NOT_RUN**.
- **Canaries attempted:** 5/5 exact topics from `video-worker/app/documentary_v2/stage_g_suite.json` (SHA-256 `30F9015A8E285D4FB1060499341256A2693AC30FE0B63E6BC0C79CF1E0E581BF`). New job IDs, attempt generation 2; rerun reason `INFRASTRUCTURE_RECOVERED`.
- **Canaries rendered:** 0. No actual MP4 exists, so actual-pixel critic and post-render technical QA were **NOT_RUN**; no metadata-only success is claimed.
- **Canaries blocked:** 0 by the text gateway in this rerun. All 5 were stopped by the existing fail-closed research/preflight path before render.
- **Canaries failed before render:** 5. Three `UNSUPPORTED_CENTRAL_CLAIM` preflight rejections (`STORY` primary cluster); two unresolved high-risk final-claim errors in `topic_review` (`UNCLASSIFIED` primary cluster under the existing mapper).
- **Canaries pending human review:** 0 produced MP4s. All five human-review artifacts say `Decision: NOT_RUN`; no human acceptance is inferred.
- **Infrastructure failures:** 0 terminal AIRouter/connection failures in generation 2. The first three jobs additionally recorded `VLM_UNAVAILABLE` / `remote_vision_available=false` as secondary diagnostics, but terminated on unsupported central claims before visual verification. This does **not** prove a VLM request was rate-limited; no critic VLM call was recorded.
- **Creative/integrity failures:** 5 non-infrastructure terminal failures: 3 `STORY` and 2 unresolved high-risk claims recorded as `UNCLASSIFIED`. The existing mapper was not changed or reinterpreted.
- **VLM rate limits:** 0 observed HTTP rate-limit events; 3 secondary `VLM_UNAVAILABLE` codes, no rendered critic run.
- **Manual interventions:** 0 scripts/assets/final-media selections. Added only attempt-lineage metadata after jobs completed.
- **Current aggregate decision:** **CANARY_FAIL**. Zero autonomous accepted jobs and a `STORY` hard-failure cluster spanning three story types satisfy the approved failure rule. `CANARY_PASS` is impossible without produced, human-reviewed accepted MP4s.

## Generation 2 raw results

- `sg20260929-065420_4e4b31dd` — LEGO ownership; preflight `UNSUPPORTED_CENTRAL_CLAIM`; `STORY` primary, `VLM_RATE_LIMIT` secondary mapping from `VLM_UNAVAILABLE`; original `sg20260929-061651_444dde13`.
- `sg20260929-065604_a2aca835` — Walt Disney founder; preflight `UNSUPPORTED_CENTRAL_CLAIM`; `STORY` primary, same secondary VLM mapping; original `sg20260929-061725_e69901e7`.
- `sg20260929-070002_edaf818e` — glass-bottle recycling; preflight `UNSUPPORTED_CENTRAL_CLAIM`; `STORY` primary, same secondary VLM mapping; original `sg20260929-061800_5e54157c`.
- `sg20260929-070204_e724a1da` — Eiffel Tower; `topic_review` error `unresolved high-risk final claim: ffbf603729`; `UNCLASSIFIED`; original `sg20260929-061834_77b317aa`.
- `sg20260929-070502_da956a2b` — stock-buyback EPS; `topic_review` error `unresolved high-risk final claim: 45a862003d`; `UNCLASSIFIED`; original `sg20260929-061909_e6dafc04`.

Each new job has EDL, manifest, trace, attribution and human-review files. The four JSON artifacts correctly say `NOT_PRODUCED`; no EDL/provenance/MP4 content was invented. Each job also has `STAGE_G_RERUN_LINEAGE.json`. The original five job directories and their attempt-1 report/scorecard copies remain in `video-worker/video-output/stage_g/`. The current scorecard retains both generations while calculating the current decision from generation 2 only.

## Boundaries

Publish: **NO**. Auto-publish: **NO**. Global V2 enablement: **NO**. Production router, AIRouter policy, MIKO, local generation, Shot Director, VisualVerifier, creative logic and F.1.1: **UNCHANGED**. No Stage G.1 or production opt-in was started.

**STOP.** Report raw results before any creative repair. If a future run produces MP4s, humans must watch them before Stage G acceptance.
