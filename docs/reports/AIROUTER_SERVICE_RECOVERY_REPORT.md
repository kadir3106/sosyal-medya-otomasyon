# AIRouter Service Recovery Report

Date: 2026-09-29 (Europe/Istanbul)

**AIROUTER_GATEWAY_HEALTH: PASS**

| Item | Result |
| --- | --- |
| Canonical AIRouter repo | `C:\Users\Victus\projeteler\AIRouter` |
| Canonical start method on this Windows machine | Direct Node/Fastify server (`packages/server/dist/index.js`) through the existing `run_724_service.vbs` → `service_watchdog.py` launcher. The documented `install_startup.ps1` registers `AIRouter724.lnk` to launch that watchdog at Windows sign-in. |
| Docker required | **NO** for this machine's local Windows route. The README recommends Docker generally and a separate VPS production deployment uses Compose, but this local checkout has a previously used direct-Node watchdog path and prior local server logs. Docker Desktop's engine failure was not the AIRouter recovery path. |
| Port 20128 before | **NO listener**; no owning PID and no AIRouter Node process. `GET /v1/models` had connection refused. The watchdog's singleton port 20127 was also unoccupied. |
| Root cause category | **AIROUTER_PROCESS_FAILURE**. The local AIRouter server and its watchdog were not running. The AIRouter Startup shortcut was absent, so the documented automatic sign-in launch was not registered. Why that shortcut was absent is not established; no server crash or dependency failure was demonstrated in this recovery. |
| Actions taken | Inspected README, package/Compose definitions, Windows launch scripts, watchdog logs, runtime files, processes, ports, and non-secret environment settings. Started the existing `run_724_service.vbs` launcher with a hidden window. Its watchdog started the existing Node server. Ran `install_startup.ps1` to restore the documented AIRouter-only Startup shortcut. No unrelated process was killed. |
| Files changed | This report and the Windows Startup shortcut `C:\Users\Victus\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\AIRouter724.lnk` (target: `run_724_service.vbs`). AIRouter runtime logs and its existing database may be updated by normal service/smoke-test activity. No source file changed. |
| Config changed | No application `.env`, provider, alias, routing-policy, Docker, or Documentary Engine configuration was changed. The AIRouter-only Windows Startup registration was restored. |
| Port 20128 after | **YES** — `node.exe` PID 39816 listening on `0.0.0.0:20128`; `pythonw.exe` PID 43580 holds watchdog port `127.0.0.1:20127`. `GET /health` returned HTTP 200 after Startup registration. |
| GET `/v1/models` | HTTP **200**, 79 ms; configured primary alias `groq/qwen/qwen3.8-27b` was present. Existing Documentary V2 credential was used in memory; no secret value was printed. |
| Minimal text completion | `POST http://127.0.0.1:20128/v1/chat/completions` with the existing `groq/qwen/qwen3.8-27b` alias and a harmless short prompt: HTTP **200**, non-empty response **YES**. Response text was not printed. |
| Latency | Models: 79 ms; minimal completion: 768 ms. |
| AIRouter gateway health | **PASS** — listener, authenticated models route, and approved-alias text completion all passed. |
| Documentary Engine changed | **NO** |
| Stage G changed | **NO** |
| Canaries rerun | **NO** |
| Publish | **NO** |

The pre-existing Docker Desktop issue remains separate: its Linux engine did not become available, and `backend.error.json` reported an access error renaming `sailor-ingest.sock` to `.stale`. No Docker repair, reinstall, or destructive socket action was taken. That issue does not block the restored direct-Node AIRouter route.

**STOP:** This task ends at service health proof. Human confirmation is required before any Stage G rerun.
