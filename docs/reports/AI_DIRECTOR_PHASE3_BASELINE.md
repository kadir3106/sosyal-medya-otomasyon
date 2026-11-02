# AI Director Phase 3 — Baseline (pre-implementation)

**Tarih:** 2026-09-23  
**Mod:** read-only survey (kod değişikliği yok)  
**Phase 2:** FREEZE — visual planning / gate / retrieval / AIRouter dokunulmayacak

---

## Pipeline (audio/caption path today)

```
generate_script
 → synthesize_speech (ElevenLabs → Edge)
 → write_ass (legacy; Director skips hook here)
 → get_or_create_bgm (random / synthetic ambient)
 → plan_scene_schedule(audio_duration)
 → [DIRECTOR] plan_and_fetch_scenes + rewrite write_ass (Hook Director)
 → [ENABLE_SFX] build_sfx_track(transition_times, word_boundaries)
 → render_video(speech + sfx + bgm amix, bgm_volume=0.15)
 → pending (approval unchanged)
```

---

## 12 soru — cevaplar

### 1. TTS provider nasıl seçiliyor?
`tts.synthesize_speech`: `ELEVENLABS_API_KEY` varsa ElevenLabs dener; başarı → `provider=elevenlabs`. Aksi / fail → Edge Neural. Pipeline `VIDEO_VOICE` / `VIDEO_VOICE_RATE` yalnız Edge’e gider.

### 2. ElevenLabs voice / settings?
- Voice: `ELEVENLABS_VOICE_ID` veya default `JBFqnCBsd6RMkjVDRZzb` (George)
- Model: `eleven_multilingual_v2`
- **Gönderilen (hard-coded):** `stability=0.55`, `similarity_boost=0.80`, `style=0.25`, `use_speaker_boost=True`
- **Yok / unused:** `speed`, Edge `rate`, env ile ayarlanabilir voice params

### 3. Edge fallback?
Missing key → hemen Edge (`edge_reason=missing_key`). API/parse fail → Edge (`elevenlabs_failed`). Boş WordBoundary → hard fail (captionless video reddedilir). Quality: `tts_edge_fallback`.

### 4. Word timestamps nereden?
Her iki provider → `[{offset, duration, text}]` (100-ns ticks). ElevenLabs: karakter alignment → kelime birleştirme. Edge: `WordBoundary` stream. ASS + (kırık) SFX keyword path tüketir.

### 5. ASS captions?
`subtitles.write_ass`: Style `Default` (alt karaoke, MarginV 480) + opsiyonel Style `Hook` (üst, Alignment 8, MarginV 280, `\fad`, ≤1.8s). `words_per_cue=2`, `highlight=True` → kelime altın flash.

### 6. Hook vs karaoke / duplicate?
Ayrı stil/layer. `_hook_duplicates_opening_vo`: hook ∩ ilk 8 VO token ≥55% → static Hook skip. Director path: punch ≤1.6s, `hook_max_words=5`, **`karaoke_start_seconds=0.0` zorlanır** (planner değeri yazımda yok sayılır).

### 7. BGM nasıl seçiliyor?
`audio_bgm.get_or_create_bgm`: `BGM_DIR` içinden random mp3/wav; yoksa lavfi sine `default_ambient.mp3`. **Mood/vocal filter yok.** Cinematic `bgm_volume=0.15`.

### 8. BGM volume?
Sabit `0.15` (cinematic) / `0.18` (split). Filter: `volume={bgm_volume},aloop` → `amix`.

### 9. SFX?
`ENABLE_SFX` (default true). Whoosh @ `scene_transition_times` (xfade offset). Keyword cash/impact/shutter — **BUG:** TTS `offset` tick kullanır, SFX `start` arar → keyword SFX fiilen ölü. Beat `audio_cue` / `emphasis_cue` parse edilir ama **hiç tüketilmez**. SFX bus `volume=0.35`.

### 10. Normalization / ducking?
**Yok.** Yalnızca sabit `volume=` + `amix duration=first`. `loudnorm` / `sidechaincompress` yok.

### 11. Scene/beat timing ↔ narration?
Master clock = **speech file duration**. `plan_scene_schedule` (rhythm: ilk 3×1.6s, mid 2.2s, tail ≥2.6s). Director beat süreleri clip materialize; render `-stream_loop` + `trim` ile sahne süresine çeker. Word-offset → cut binding **yok**.

### 12. Retention pacing nerede?
`render.py` `RHYTHM_*` sabitleri + `SCENE_CLIP_DURATION` / xfade + Edge `+12%` rate. Caption punch süreleri. Retention modeli / semantic pacing controller **yok**.

---

## Phase 2 FREEZE vs Phase 3 touch

| FREEZE | Phase 3 safe |
|--------|----------------|
| `director.py`, `director_planner.py`, `director_gate.py` (gate/retrieval mantığı) | `tts.py`, `subtitles.py`, `sfx.py`, `audio_bgm.py` |
| AIRouter routing / providers | `render.py` **audio** mix section |
| Telegram / pending / publishers | `pipeline.py` wiring + `config.py` flags |
| Visual beat semantics / scoring | Consume existing `audio_cue` / hook metadata only |

`director_types` / planner: yalnız mevcut `audio_cue` alanlarını **tüketmek** OK; storyboard şemasını yeniden yazmak değil.

---

## Phase 3 gap’ler (implementation hedefleri)

1. NarrationProfile (tek batch / deterministic; ek LLM call yok veya planning’ten türet)
2. ElevenLabs supported params config’lenebilir (speed yoksa uydurma)
3. Semantic caption chunking + emphasis + safe zone
4. Hook: duplicate yok, VO+caption t≈0, spam title yok
5. Instrumental BGM preference / vocal avoid
6. FFmpeg ducking (VO > BGM) + güvenli loudness
7. SFX: `offset` fix + beat `audio_cue` budget (az, anlamlı)
8. Feature flags: `PHASE3_*` rollback
9. Mux `-t` / stream_loop regression koru

---

## Riskler (bozulmaması gerekenler)

- WordBoundary boş → job abort
- `-shortest` geri gelmemeli
- Hook duplicate-skip + karaoke-from-t=0
- River / bakery / anti-repetition gate
- Pending/approval contract
- AIRouter call sayısı patlamamalı (cümle başına LLM yok)
