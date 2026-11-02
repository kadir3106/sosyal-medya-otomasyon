# AI Director Phase 2 — Main MP4 `-shortest` Mux Fix

**Tarih:** 2026-09-23  
**Kapsam:** Yalnızca `video-worker/app/render.py` mux (Director / gate / AIRouter / Telegram / Phase 3 yok)  
**Job:** `20260923-082227` (Phase 2.2 FINAL E2E artifact re-render; yeni LLM yok)

---

## Before / After

| | Before | After |
|--|--------|-------|
| Main container | **≈2.23 s** | **≈26.47 s** |
| Main video stream | ≈2.23 s (67 frames) | **≈26.47 s (794 frames)** |
| Main audio stream | ≈2.22 s | **≈26.45 s** |
| Intended timeline | ≈26.45 s (audio / scene plan) | ≈26.45 s |
| Splitscreen (kontrol) | ≈26.43 s | ≈26.43 s (değişmedi) |

Artifact: [`video-output/AI_DIRECTOR_PHASE2_RENDER_FIX_20260923-082227.mp4`](video-output/AI_DIRECTOR_PHASE2_RENDER_FIX_20260923-082227.mp4)

---

## Root cause

`render_video` FFmpeg cmd used **`-shortest`**.

FFmpeg semantics: encoding ends when the **shortest input demux stream** ends — not when the filtergraph timeline ends.

Phase 2 Director still→motion clips are written at `SCENE_CLIP_DURATION = 2.2s` (`image_to_motion_clip`). Scene schedule then stretches scenes to cover narration (~26s) via trim/pad in the filtergraph.

**Truncating input:** each `clip_*.mp4` demux ≈ **2.2 s**  
**Planned timeline:** `_covered_duration(scenes, xfade)` ≈ **audio ≈ 26.45 s**  
**Effect of `-shortest`:** encode aborted at first short clip → main video **and** mapped audio both cut to ≈2.2 s.

Splitscreen already avoided this with `-stream_loop -1` on video inputs + **`-t audio_dur`**.

Secondary issue found while fixing: `tpad` + `xfade` alone did **not** reliably emit full padded video frames after removing `-shortest` (container/audio reached ~26s but video stream stayed ~5.7s). Inputs needed looping so scene `trim` can always fill `scene_duration`.

---

## Fix (minimal)

In `video-worker/app/render.py`:

1. **Remove `-shortest`.**
2. Cap output with **`-t {max(timeline_duration, audio_duration)}`.**
3. Prefix video inputs with **`-stream_loop -1`** (stills: `-loop 1`) so short demux files cannot starve scene trims.
4. Scene filter tail: `trim=duration=…,setpts,fps` (no `tpad` dependency).

Director planning, gates, AIRouter, Telegram, publishers untouched.

---

## Regression test

`tests/test_render.py`:

- `test_render_video_uses_timeline_t_not_shortest` — cmd has `-t`, no `-shortest`, has `-stream_loop`
- `test_render_video_final_duration_not_truncated_by_short_clip_inputs` — real ffmpeg: **1.0s clips** + **6.0s audio** → format **and** video stream ≈ intended timeline (±0.5s), not ≈1s

```
tests/test_render.py — 21 passed
```

---

## Re-render / verify

- Source: existing job audio (from splitscreen) + pending Pexels asset IDs → rebuilt clips  
- No new LLM / storyboard  
- Pending remains **unpublished** (`approved=None`)

### ffprobe (after)

**Main `20260923-082227.mp4`**
- format: **26.466667**
- video: **26.466667** (794 frames @ 30fps)
- audio: **26.452993**

**Splitscreen (unchanged control)**
- format: **26.433333**
- video: **26.433333**
- audio: **26.424000**

Also checked: ASS dialogues present in re-render work dir; visual beats (7 clips) present through final scene; pending/approval behavior unchanged.

---

## Durum

**Mux blocker fixed.** Phase 2 visual architecture freeze can proceed.  
**Phase 3’e geçilmedi.**
