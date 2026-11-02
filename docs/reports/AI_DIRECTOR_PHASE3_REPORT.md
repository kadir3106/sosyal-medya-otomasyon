# AI Director Phase 3 — Report

**Tarih:** 2026-09-23  
**Job:** `20260923-124217`  
**REAL LLM PLANNING:** PASS  
**Publish:** yok (pending/approval unchanged)  
**Phase 2 visual freeze:** korundu (director_gate / retrieval / AIRouter routing dokunulmadı)

---

## Verdict

Phase 3 audio/caption/music katmanı uygulandı, feature-flag’li, tests yeşil, Rolex real E2E üretildi.

| Check | Result |
|-------|--------|
| REAL LLM → AIRouter | PASS (`gemini-flash` → `gemini/gemini-3.6-flash`, fb=0, 2 calls) |
| Main duration ≈ audio | PASS (~24.63s video / ~24.62s audio) |
| Mux truncate | PASS (stream_loop + `-t` korundu) |
| River / bakery | PASS (selected clean) |
| Anti-repetition consecutive | PASS |
| Pending unpublished | PASS |
| ElevenLabs | Edge fallback (`tts_edge_fallback`) — settings path hazır |

**Video:** [`video-output/AI_DIRECTOR_PHASE3_REAL_E2E_20260923-124217.mp4`](video-output/AI_DIRECTOR_PHASE3_REAL_E2E_20260923-124217.mp4)

---

## Baseline findings

See [`AI_DIRECTOR_PHASE3_BASELINE.md`](AI_DIRECTOR_PHASE3_BASELINE.md).

Özet gaps closed:
- ElevenLabs settings hard-coded → profile/env merge (supported keys only)
- Keyword SFX `offset` bug → fixed
- No instrumental BGM preference → filename heuristic + ambient fallback
- No ducking → `sidechaincompress` when `PHASE3_MUSIC_ENABLED`
- Captions fixed 2-word flash → semantic chunks + selective emphasis
- No profiles → deterministic Narration/Pacing/Music (0 extra LLM)

---

## Files changed

| File | Role |
|------|------|
| `app/phase3_profiles.py` | **NEW** — Narration/Pacing/Music profiles |
| `app/config.py` | `PHASE3_*` flags + optional ElevenLabs overrides |
| `app/tts.py` | voice_settings merge (no invented `speed`) |
| `app/subtitles.py` | Caption V2 (chunks, emphasis, safe MarginV, legacy header if flag off) |
| `app/audio_bgm.py` | instrumental preference / vocal name avoid |
| `app/sfx.py` | offset-ticks fix, budget, audio_cue consume |
| `app/render.py` | duck_bgm + optional loudnorm (visual mux untouched) |
| `app/pipeline.py` | wire profiles/flags only |
| `tests/test_phase3.py` | **NEW** regressions |

**Not touched:** `director.py`, `director_gate.py`, `director_planner.py` (logic), AIRouter, publishers, Telegram, MİKO, Bonsai.

---

## Architecture (Phase 3)

```
script
 → NarrationProfile / MusicProfile / PacingProfile  (deterministic)
 → TTS (ElevenLabs settings from profile → Edge fallback)
 → ASS V2 (semantic chunks + emphasis; hook duplicate-skip)
 → BGM (instrumental prefer, lower volume)
 → SFX (budget; offset-fixed keywords; optional beat cues)
 → render mix (sidechain duck + loudnorm) + Phase 2 visuals
 → pending
```

Flags (default `true`; set `false` to rollback that layer):
- `PHASE3_AUDIO_ENABLED`
- `PHASE3_CAPTIONS_ENABLED`
- `PHASE3_MUSIC_ENABLED`
- `PHASE3_RETENTION_ENABLED`

---

## Profiles (this E2E)

**NarrationProfile**
```json
{
  "style": "premium_documentary",
  "energy": 0.78,
  "pace": "controlled_fast",
  "dramatic_level": 0.77,
  "pause_strength": 0.5,
  "emphasis": ["Rolex", "Hans Wilsdorf", "Geneva", "Swiss", "Billions", …]
}
```

**MusicProfile**
```json
{
  "mood": "dark_luxury",
  "intensity": 0.55,
  "vocals_allowed": false,
  "bgm_volume": 0.09,
  "duck_threshold": 0.02,
  "duck_ratio": 7.0
}
```

**PacingProfile** — semantic labels only (visual beat timing not rewritten).

---

## Caption / ducking / SFX

- Karaoke from VO start (`karaoke_start_seconds=0`)
- Hook punch: `THE ROLEX TRUST SECRET` ≤1.5s; duplicate-skip retained
- Safe zone: Default MarginV **440** (Phase 3 header)
- BGM ducked under VO via sidechaincompress
- SFX: whoosh budget capped; keyword path uses TTS `offset` ticks; beat `audio_cue` count this run: **0**
- Loudness (ebur128): **I ≈ −15.8 LUFS**, LRA ≈ 2.0 LU

---

## Tests

```
tests/test_phase3.py + render + subtitles + gate + phase21/22
56 passed
```

Includes: caption start near VO, chunking, hook duplicate skip, instrumental prefer, vocal avoid, BGM volume < narration bus, SFX offset, sidechain duck, mux short-clip guard, bakery/river symbols present.

---

## AIRouter route (E2E)

| Call | Requested | Resolved | Tokens | Latency | fb |
|------|-----------|----------|--------|---------|-----|
| script | gemini-flash | gemini / gemini-3.6-flash | 1138+707 | 25.0s | 0 |
| storyboard | gemini-flash | gemini / gemini-3.6-flash | 1283+4250 | 42.6s | 0 |

**AIRouter calls:** 2 (Phase 2 ile aynı sınıf — Phase 3 ekstra LLM yok)  
**TTS calls:** 1 (Edge fallback; ElevenLabs fail → mevcut davranış)

---

## Before / after metrics

| Metric | Phase 2 FINAL (`082227` / render-fix) | Phase 3 (`124217`) |
|--------|----------------------------------------|---------------------|
| Main duration | ~26.47s | **24.63s** |
| Audio duration | ~26.45s | **24.62s** |
| Video frames | 794 | 739 |
| Engine | director | director |
| Beats | 14 | 10 |
| Clips / reuse | 7 / 1.0 | 7 / 1.0 |
| River/bakery | clean | clean |
| BGM volume target | 0.15 flat | **0.09 + duck** |
| Caption mode | Phase 2 karaoke | Phase 3 chunks+emphasis |
| Integrated loudness | (unmeasured) | **−15.8 LUFS** |
| AIRouter calls | 2 | **2** |
| Generate wall time | ~146–580s | ~918s (loudnorm+duck heavier) |

---

## Known limitations

1. **ElevenLabs** bu E2E’de Edge’e düştü — voice_settings uygulanamadı; path/test hazır.
2. Emphasis listesinde topic-fragment gürültü (`How Rolex`, `You`) — heuristic; ileride sıkılaştırılabilir.
3. `audio_cue` beat’lerde boş → SFX çoğunlukla whoosh budget; Cue üretimi planner’da Phase 2 freeze nedeniyle zorlanmadı.
4. Loudnorm + sidechain render süresini uzatır.
5. Work dir ASS job sonunda silinmiş olabilir; burn-in videoda.

---

## Durum

**Phase 3 implementation + tests + REAL E2E + report hazır.**  
Video’yu insan değerlendirmesi için bırakıyorum.

**Phase 4 / Bonsai / Ollama / MİKO / AIRouter routing / publishers: dokunulmadı. DUR.**
