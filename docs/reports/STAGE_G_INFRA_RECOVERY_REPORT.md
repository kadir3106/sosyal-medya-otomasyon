# Stage G Infrastructure Recovery Report

Date: 2026-09-29 (Europe/Istanbul)

Status: **BLOCKED — TEXT_GATEWAY_HEALTH = FAIL**. The fail-closed pre-rerun gate prevented new Stage G jobs.

- **Root cause:** Nothing listens on the configured local AIRouter port 20128. TCP connection to `127.0.0.1:20128` failed and `GET /v1/models` returned connection refused. The deeper reason the AIRouter service is absent has not been proven. Docker Desktop was initially stopped; an attempt to start the already installed application launched its processes but not its Linux engine. Docker's `backend.error.json` reports an access failure while renaming `sailor-ingest.sock` to `.stale` during Ingest server initialization. Whether this Docker failure is the direct cause of AIRouter being down remains unverified because the engine never became available to inspect its containers.
- **Effective gateway before:** `http://127.0.0.1:20128/v1/chat/completions` (repository `.env` has `LLM_API_URL=http://127.0.0.1:20128/v1`; `script_gen._resolve_url` appends `/chat/completions`). The repository `.env.example` explicitly documents this host endpoint and `host.docker.internal:20128` for Docker. An earlier repository E2E report also identifies production AIRouter at port 20128.
- **Effective gateway after:** Unchanged: `http://127.0.0.1:20128/v1/chat/completions`.
- **Service started/recovered:** Docker Desktop start attempted; Docker engine did not start. AIRouter not recovered. No AIRouter process/container was started or modified.
- **Config changed:** No. No endpoint, model, provider, routing, fallback, or secret setting changed.
- **Files changed:** This report only. No application code, AIRouter code, Stage F.1.1, MIKO, creative logic, or existing Stage G output was edited.
- **Smoke test:** **FAIL**. No TCP listener on port 20128; `GET http://127.0.0.1:20128/v1/models` returned connection refused. The configured primary model alias is `groq/qwen/qwen3.8-27b` and configured fallback is `gemini-flash`; neither was called. Chat/completions-compatible request, minimal text routing, and response latency are **NOT_TESTED / NOT_AVAILABLE** because the endpoint is unreachable. No secret values were printed.
- **Focused regression:** Not rerun; no application/configuration integration change occurred. The prior Stage G focused result remains 123 passed, 1 warning, but it is not a new verification result.
- **Full suite:** NOT_RUN; no full-suite PASS claim.
- **Canaries rerun:** 0/5. The exact five original topics were not replaced or retried because `TEXT_GATEWAY_HEALTH` did not pass. No new job IDs or rerun lineage exist yet. The five original infrastructure-blocked job directories and the existing aggregate report/scorecard remain intact and unchanged at `video-worker/video-output/stage_g/` (`CANARY_PARTIAL`, infrastructure blocked 5/5).
- **Publish:** No.
- **Global V2 enable:** No.

## Stop condition and next required action

Restore the existing AIRouter service at its documented endpoint and confirm a successful minimal `/v1/chat/completions` response for the configured alias before creating any rerun jobs. The Docker socket access error is an infrastructure issue to resolve without changing AIRouter routing code or silently bypassing the gateway. Once connectivity is proven, rerun the same five topics under new job IDs, retain the original attempts, and update the aggregate package with both sets of outcomes. Human review of actual MP4s is still required for acceptance.
