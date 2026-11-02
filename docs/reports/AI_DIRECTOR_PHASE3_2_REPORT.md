# AI Director Phase 3.2 — Final Polish Report

**Date:** 2026-09-23  
**Job:** `20260923-203255`  
**Scope:** Final polish only (vocal BGM + visual-information hold). Not Phase 4.  
**Publish:** none — pending only  
**Phase 2 freeze:** preserved

---

## Verdict — awaiting human review

| Check | Result |
|-------|--------|
| Vocal BGM | **PASS** — verified instrumental only (`default_ambient.mp3`) |
| Music mood | `financial_documentary`, `vocals_allowed=false` |
| Hans portrait | **PASS** (`wiki:4bb4b8e9453e` @ ~7.0–8.8s) |
| Wall Street contextual | **PASS** (Pexels @ ~12.0s) |
| Long visual-info hold | **improved** — longest info interval **1.8s** (was ~10s human-reported 0:08–0:18) |
| Random B-roll | not introduced |
| Captions / mux / pending | unchanged paths |
| Tests | `test_phase32` + phase3/31/river green |

**Do not AUTO-ACCEPT.** Human review required.

---

## Outputs

| Artifact | Path |
|----------|------|
| Video | [`video-output/AI_DIRECTOR_PHASE3_2_FINAL_20260923-203255.mp4`](video-output/AI_DIRECTOR_PHASE3_2_FINAL_20260923-203255.mp4) (~23.4s) |
| Trace | [`video-output/AI_DIRECTOR_PHASE3_2_TRACE_20260923-203255.json`](video-output/AI_DIRECTOR_PHASE3_2_TRACE_20260923-203255.json) |
| Compare (3.1) | `AI_DIRECTOR_PHASE3_1_REAL_E2E_20260923-194336.mp4` (~25.5s) |

---

## 1) Why vocal track passed previously

`get_or_create_bgm` used:

```text
instrumental = looks_instrumental_track(name)
non_vocal = not looks_vocal_track(name)
pool = instrumental or non_vocal
```

Any file **without** the substring `vocal`/`lyrics`/… in the **filename** entered `non_vocal` and could be selected — even J-Pop / song tracks with clean filenames or misleading names.

Metadata was not checked. Ambiguous tracks were treated as safe.

In this environment the library often only had `default_ambient.mp3` (synthetic lavfi pad). Human-heard “J-Pop-like” vocals may have come from:

1. A previously dropped library track that passed the loose `non_vocal` filter, and/or  
2. Perception of bright synthetic/edge-TTS mix under ducking  

Regardless, selection is now fail-closed for documentary.

---

## 2) How vocal rejection works now

When `vocals_allowed=False` (documentary default):

1. Reject filename vocal cues (`vocal`, `song`, `lyrics`, `singing`, `jpop`, …)
2. Reject ffprobe tag cues (`title`/`genre`/`comment` containing vocal/song/pop/…)
3. Accept only **verified instrumental** names (`ambient`, `cinematic`, `score`, `default_ambient`, …) or known synthetic ambient
4. Else generate/keep synthetic `default_ambient` (no vocals)
5. Else **silence** (`bgm_path=None`) — preferred over wrong music

Mood ranks verified instrumentals (`financial_documentary` → cinematic/dark/tension/ambient).

---

## 3) Selected music (this E2E)

```json
{
  "bgm_path": "/data/media/audio/bgm/default_ambient.mp3",
  "reason": "verified_instrumental:financial_documentary",
  "vocals_allowed": false,
  "mood": "financial_documentary",
  "prefer_instrumental": true,
  "rejected_tracks": []
}
```

Ducking + loudnorm unchanged.

---

## 4) Long-hold root cause (0:08–0:18 in 3.1)

Phase 3.1 measured **same `asset_id`**, not **same visual information**.

Different Pexels Rolex-box IDs still felt like one slideshow. Zoom/`punch_in` reset “novelty” without new meaning.

### Fix
- `visual_info_key()` buckets: `product_hero`, `ownership_structure`, `finance_reserve`, `person_archive`, …
- Long product-hero hold + new claim → `contextual_cutaway` (gated new queries; fail → hold/transform, never random B-roll)
- Zoom alone ≠ new information

This E2E: longest visual-info interval **1.8s**; timeline alternates product → ownership → Hans → Wall Street → tax → Swiss place.

---

## 5) Retention events (trace)

| type | reason |
|------|--------|
| archive_reveal | named person (Hans) |
| archive_reveal | (second person/entity path) |
| number_emphasis | financial/number claim |

Cutaway machinery armed; this script already shifted info keys early so fewer cutaways fired — hold problem still addressed.

---

## 6) Tests

`tests/test_phase32.py` covers:

1–4 vocal reject / instrumental / ambiguous / silence  
5–7 cutaway / unrelated queries / zoom≠info  
8–9 person portrait + Hans generic  
10–11 river/bakery  
12–15 captions, mux import, pending  

Also `test_phase3` + `test_phase31` + river suite: green.

---

## 7) Ops notes

| Item | Value |
|------|--------|
| TTS | edge (ElevenLabs fallback — separate) |
| AIRouter | real LLM path (Director + script); routing unchanged |
| Duration | ~23.4s main |
| Pending | yes, unpublished |

### Known limitations
- Library has few real dark-score tracks → synthetic ambient is the verified instrumental fallback
- Some beats still miss gated stock (fail-closed)
- `Fondation Hans Wilsdorf` org entity correctly skipped as person

---

## STOP

Video + trace + report ready.  
**No Phase 4. No freeze declaration. Awaiting human review.**
