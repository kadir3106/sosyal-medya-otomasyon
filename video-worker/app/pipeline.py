import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from app.audio_bgm import get_or_create_bgm
from app.config import config
from app.errors import FalAuthBillingError, KlingAuthBillingError
from app.image_gen import render_card
from app import jobs as job_store
from app.joblog import log_event
from app.render import (
    get_audio_duration,
    plan_scene_schedule,
    render_video,
    scene_transition_times,
)
from app.script_gen import generate_script
from app.script_quality import merge_into_script_dict, refine_script
from app.stock_media import extract_keywords, fetch_stock_clips, resolve_scene_queries

from app.subtitles import write_ass
from app.topics import release_topic, resolve_en_topics_path, select_next_topic
from app.tts import synthesize_speech
from app.phase3_profiles import (
    build_music_profile,
    build_narration_profile,
    build_pacing_profile,
)

# Sahne süresi/geçiş süresi — render.py ile AYNI değerler kullanılmalı.
SCENE_CLIP_DURATION = 2.2
SCENE_XFADE_DURATION = 0.4

# Sahne sayısı artık sabit değil: ses süresinden hesaplanır (bkz. plan_scene_schedule).
# Bu yalnızca emniyet tavanı — 90 sn'lik ses bile bu sayının altında kalır.
MAX_SCENES = 40
# Stock: her sahne = Pexels/Pixabay indirmesi (~30s). Cap scenes so jobs finish
# in minutes; render stretches durations via plan_scene_schedule(max_scenes=...).
STOCK_MAX_SCENES = 8

# Tekrar oranı bu eşiği aşarsa video "slayt gösterisi" hissi verir; sessizce
# yayınlanmasındansa gürültü çıkarması daha iyidir.
# clip_reuse_ratio = scenes / unique_clips (1.0 = her sahne ayrı klip).
MAX_CLIP_REUSE_RATIO = 1.35

# Fraction of Pexels downloads that came from already-used clip IDs.
# >0.35 ≈ shipping stale unrelated wealth stock — hard-fail and regenerate.
MAX_STOCK_CACHE_REUSE_RATIO = 0.35

FAL_AUTH_BILLING_TELEGRAM = (
    "Fal/Flux/Kling API 403 Forbidden - Bakiye veya Yetki Hatası! Üretim durduruldu."
)
# Geriye dönük alias (önceki Kling hard-fail dokümanı / testler).
KLING_AUTH_BILLING_TELEGRAM = FAL_AUTH_BILLING_TELEGRAM


def _notify_fal_auth_billing_fail(
    job_id: str,
    exc: FalAuthBillingError | KlingAuthBillingError,
) -> None:
    """Structured log + optional Telegram critical alert (no secrets)."""
    log_event(
        job_id,
        "kling_auth_or_billing_fail",
        status_code=exc.status_code,
        detail=exc.detail,
        error=str(exc),
        engine=str(getattr(config, "VISUAL_ENGINE", "unknown")),
    )
    print(
        f"[pipeline] HARD-FAIL: Fal auth/billing "
        f"(HTTP {exc.status_code}) — Pexels catch-all YOK. Job failed.",
        flush=True,
    )
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat_id:
        return
    try:
        from app.telegram_bot import send_message

        send_message(
            token,
            chat_id,
            f"🚨 *{FAL_AUTH_BILLING_TELEGRAM}*\n\n"
            f"`job_id`: `{job_id}`\n"
            f"`http`: `{exc.status_code}`\n"
            f"`engine`: `{getattr(config, 'VISUAL_ENGINE', '?')}`",
        )
    except Exception as notify_err:
        print(f"[pipeline] Telegram auth/billing alert failed: {notify_err}", flush=True)


def _notify_telegram_awaiting_approval(result: dict) -> None:
    """Worker-side Telegram sendVideo + Onayla/Reddet (curl /generate path).

    n8n workflow also sends video; duplicate is acceptable — approve still required
    before YT/TikTok/IG publish. No-op when token/chat missing.
    """
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat_id:
        print("[pipeline] Telegram notify skipped (token/chat boş).", flush=True)
        return
    video_path = result.get("video_path") or ""
    if not video_path or not Path(video_path).is_file():
        print("[pipeline] Telegram notify skipped (video yok).", flush=True)
        return
    try:
        from app.telegram_bot import send_video

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Onayla & Yayınla", "callback_data": "approve"},
                    {"text": "❌ Reddet", "callback_data": "reject"},
                ]
            ]
        }
        send_video(
            token,
            chat_id,
            video_path,
            caption=format_approval_caption(result),
            reply_markup=keyboard,
        )
        log_event(result.get("job_id") or "unknown", "telegram_approval_sent")
    except Exception as notify_err:
        print(f"[pipeline] Telegram approval notify failed: {notify_err}", flush=True)


def _extract_hook(script: str, max_words: int = 12) -> str:
    """First sentence (or first N words) for Telegram QA / job telemetry."""
    text = " ".join((script or "").split())
    if not text:
        return ""
    for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        if sep in text:
            text = text.split(sep, 1)[0].rstrip(".!?") + sep.strip()
            break
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "…"
    return text


def format_approval_caption(result: dict) -> str:
    """Compact Turkish approval card: title, desc, hook + reuse + TTS + warning."""
    title = result.get("title") or ""
    description = result.get("description") or ""
    q = result.get("quality") or {}
    hook = q.get("hook") or ""
    reuse = q.get("clip_reuse_ratio")
    tts = q.get("tts") or "?"
    engine = q.get("engine") or "?"
    warning = q.get("warning") or ""

    lines = [f"🎬 *{title}*", ""]
    if description:
        lines.append(description)
        lines.append("")
    if hook:
        lines.append(f'🪝 Hook: _"{hook}"_')
    reuse_s = f"{reuse}x" if isinstance(reuse, (int, float)) else "?"
    lines.append(f"⚙️ tekrar {reuse_s} · TTS `{tts}` · {engine}")
    if warning:
        if warning == "clip_reuse_ratio_high":
            lines.append("⚠️ TEKRAR YÜKSEK — slayt hissi riski")
        elif warning == "tts_edge_fallback":
            lines.append("⚠️ Edge TTS — ses kalitesi düşük (ElevenLabs önerilir)")
        else:
            lines.append(f"⚠️ {warning}")
    elif tts == "edge":
        lines.append("ℹ️ Edge TTS kullanıldı (kalite yolu: ElevenLabs)")
    lines.append("")
    lines.append("Yukarıdaki videoyu onaylıyor musun?")
    return "\n".join(lines)


async def generate_video(job_id: str, topic: str | None = None) -> dict:
    """Async entrypoint — offloads the blocking pipeline so the event loop
    (Telegram poller, health, digest) stays responsive during Kling/FFmpeg."""
    return await asyncio.to_thread(_generate_video_sync, job_id, topic)


def _generate_video_sync(job_id: str, topic: str | None = None) -> dict:
    media_dir = Path(config.MEDIA_DIR)
    work_dir = media_dir / "work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    state_path = str(media_dir / "used_topics.json")
    lang = config.VIDEO_LANG if config.VIDEO_LANG in ("en", "tr") else "en"
    if lang == "tr":
        topics_path = config.TOPICS_PATH_TR
    else:
        raw_path = config.TOPICS_PATH
        if not isinstance(raw_path, str) or not raw_path.strip():
            raw_path = "/app/data/topics_dark_wealth.json"
        topics_path = resolve_en_topics_path(raw_path)
    voice = config.VIDEO_VOICE or ("tr-TR-EmelNeural" if lang == "tr" else "en-US-GuyNeural")

    started_at = time.monotonic()
    from_pool = topic is None
    try:
        from app.documentary_v2 import pipeline_mode_diagnostics

        _pm = pipeline_mode_diagnostics()
        print(
            f"[pipeline] job={job_id} pipeline_mode={_pm['pipeline_mode']} "
            f"DOCUMENTARY_ENGINE_V2={_pm['documentary_engine_v2']} "
            f"DIRECTOR_ENABLED={_pm['director_enabled']}",
            flush=True,
        )
        log_event(job_id, "pipeline_mode", **_pm)

        job_store.create_job(
            media_dir, job_id, kind="video", state="generating", topic=topic
        )
        if from_pool:
            topic = select_next_topic(topics_path, state_path)
            job_store.update_job(media_dir, job_id, topic=topic)
        log_event(job_id, "topic_selected", topic=topic, lang=lang, topics_path=topics_path)

        stage_started = time.monotonic()
        winning_context = None
        if config.ENABLE_ANALYTICS_MEMORY:
            parts: list[str] = []
            try:
                from app.channel_growth import get_winning_context_for_prompt

                yt_ctx = get_winning_context_for_prompt()
                if yt_ctx:
                    parts.append(yt_ctx)
            except Exception:
                pass
            try:
                from app.analytics_memory import format_hook_memory_context

                stub_ctx = format_hook_memory_context(media_dir)
                if stub_ctx:
                    parts.append(stub_ctx)
            except Exception:
                pass
            winning_context = "".join(parts) or None

        if winning_context:
            script_data = generate_script(
                topic,
                api_key=config.OPENROUTER_API_KEY,
                lang=lang,
                winning_context=winning_context,
            )
        else:
            script_data = generate_script(
                topic,
                api_key=config.OPENROUTER_API_KEY,
                lang=lang,
            )
        log_event(
            job_id, "script_generated",
            title=script_data["title"],
            word_count=len(script_data["script"].split()),
            hook_selected=script_data.get("hook_selected"),
            hook_alternatives=script_data.get("hook_alternatives"),
            seconds=round(time.monotonic() - stage_started, 1),
        )

        # Script quality + fact verification (before TTS). Fail-closed on HIGH risk.
        stage_started = time.monotonic()
        raw_before_quality = script_data.get("script") or ""
        quality_result = refine_script(raw_before_quality, topic=topic)
        script_data = merge_into_script_dict(script_data, quality_result)
        if not (script_data.get("script") or "").strip():
            raise RuntimeError(
                "script_quality_empty_after_verification — refusing to TTS/publish "
                "unsupported high-risk claims"
            )
        # Persist trace outside work_dir (work_dir is deleted in finally).
        try:
            trace_path = media_dir / f"SCRIPT_QUALITY_TRACE_{job_id}.json"
            trace_path.write_text(
                json.dumps(quality_result.to_dict(), indent=2, ensure_ascii=False)[:400000],
                encoding="utf-8",
            )
        except Exception as trace_err:
            print(f"[pipeline] script quality trace write failed: {trace_err}", flush=True)
        try:
            sd_path = media_dir / f"SOURCE_DIVERSITY_TRACE_{job_id}.json"
            sd_path.write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "topic": topic,
                        "script_quality": quality_result.to_dict(),
                        "story_consistency": quality_result.story_consistency,
                        "replacement_intents": quality_result.replacement_intents,
                        "replacement_research": quality_result.replacement_research,
                    },
                    indent=2,
                    ensure_ascii=False,
                )[:400000],
                encoding="utf-8",
            )
        except Exception as sd_err:
            print(f"[pipeline] source diversity early trace failed: {sd_err}", flush=True)
        log_event(
            job_id,
            "script_quality_done",
            word_count=len(script_data["script"].split()),
            estimated_duration=quality_result.estimated_duration,
            verification_outage=quality_result.verification_outage,
            review_required=quality_result.review_required,
            llm_calls=quality_result.llm_calls,
            search_calls=quality_result.search_calls,
            decisions=(quality_result.verification_summary or {}).get("decisions"),
            seconds=round(time.monotonic() - stage_started, 1),
        )

        hook_text = (
            quality_result.hook
            or script_data.get("hook_selected")
            or _extract_hook(script_data["script"])
        )
        narration_profile = build_narration_profile(
            topic=topic,
            script=script_data.get("script") or "",
            hook=hook_text or "",
            concrete_nouns=script_data.get("concrete_nouns"),
        )
        music_profile = build_music_profile(
            topic=topic, script=script_data.get("script") or ""
        )
        pacing_profile = build_pacing_profile(script=script_data.get("script") or "")
        phase3_audio = bool(getattr(config, "PHASE3_AUDIO_ENABLED", False))
        phase3_caps = bool(getattr(config, "PHASE3_CAPTIONS_ENABLED", False))
        phase3_music = bool(getattr(config, "PHASE3_MUSIC_ENABLED", False))
        phase3_ret = bool(getattr(config, "PHASE3_RETENTION_ENABLED", False))

        audio_path = str(work_dir / "speech.mp3")
        stage_started = time.monotonic()
        # synthesize_speech is async; we're already in a worker thread so
        # asyncio.run is safe (no running loop in this thread).
        tts_meta: dict = {}
        voice_settings = (
            narration_profile.elevenlabs_voice_settings() if phase3_audio else None
        )
        word_boundaries = asyncio.run(
            synthesize_speech(
                script_data["script"],
                audio_path,
                voice=voice,
                rate=config.VIDEO_VOICE_RATE,
                meta_out=tts_meta,
                voice_settings=voice_settings,
            )
        )
        tts_provider = tts_meta.get("provider") or "unknown"
        log_event(
            job_id, "tts_done",
            word_count=len(word_boundaries),
            tts=tts_provider,
            edge_reason=tts_meta.get("edge_reason"),
            phase3_audio=phase3_audio,
            seconds=round(time.monotonic() - stage_started, 1),
        )

        # TikTok / Reels tarzı dinamik kelime vurgulamalı altyazı + hook overlay.
        # Director açıkken Hook Director planı clip fetch sonrası ASS'i yeniden yazar
        # (kısa punch + karaoke gecikmesi); legacy yol aynı kalır.
        director_on_early = os.environ.get("DIRECTOR_ENABLED", "false").lower() == "true"
        subtitle_path = write_ass(
            word_boundaries,
            str(work_dir / "subs.ass"),
            words_per_cue=2,
            highlight=True,
            add_emojis=getattr(config, "ENABLE_SUBTITLE_EMOJIS", False) is True,
            hook_text=None if director_on_early else hook_text,
            hook_seconds=2.5,
            phase3=phase3_caps and not director_on_early,
            emphasis_words=narration_profile.emphasis if phase3_caps else None,
        )

        # Kalite telemetrisi (hook / TTS / motor) — Telegram + pending.json.
        quality: dict = {
            "hook": hook_text,
            "hook_alternatives": script_data.get("hook_alternatives") or [],
            "hook_selected": script_data.get("hook_selected") or hook_text,
            "tts": tts_provider,
            "engine": str(getattr(config, "VISUAL_ENGINE", "unknown")),
            "concrete_nouns": script_data.get("concrete_nouns") or [],
            "phase3": {
                "audio": phase3_audio,
                "captions": phase3_caps,
                "music": phase3_music,
                "retention": phase3_ret,
            },
            "narration_profile": narration_profile.to_dict(),
            "music_profile": music_profile.to_dict(),
            "pacing_profile": pacing_profile.to_dict(),
            "script_quality": {
                "estimated_duration": quality_result.estimated_duration,
                "verification_summary": quality_result.verification_summary,
                "llm_calls": quality_result.llm_calls,
                "search_calls": quality_result.search_calls,
                "review_required": quality_result.review_required,
                "loop_strategy": quality_result.loop_strategy,
                "raw_word_count": len(raw_before_quality.split()),
                "final_word_count": len((script_data.get("script") or "").split()),
            },
        }
        if quality_result.review_required:
            quality["review_required"] = True
            quality["review_reason"] = "script_verification_outage_or_high_risk_unknown"
        if tts_provider == "edge":
            quality["warning"] = "tts_edge_fallback"
            log_event(
                job_id, "quality_warning",
                reason="tts_edge_fallback",
                edge_reason=tts_meta.get("edge_reason", "unknown"),
            )

        video_filename = f"{job_id}.mp4"
        video_path = str(media_dir / video_filename)

        bgm_dir = config.BGM_DIR or str(media_dir / "audio" / "bgm")
        bgm_selection: dict = {}
        bgm_path = get_or_create_bgm(
            bgm_dir,
            vocals_allowed=bool(music_profile.vocals_allowed) if phase3_music else True,
            prefer_instrumental=phase3_music,
            mood=str(music_profile.mood or "") if phase3_music else "",
            allow_silence=True,
            selection_out=bgm_selection,
        )
        bgm_volume = float(music_profile.bgm_volume) if phase3_music else 0.15
        quality["bgm_selection"] = bgm_selection
        if not bgm_path:
            quality["bgm_silence"] = True
            log_event(job_id, "bgm_silence", reason=bgm_selection.get("reason"))

        thumbnail_filename = f"{job_id}_thumb.png"
        thumbnail_path = str(media_dir / thumbnail_filename)

        if getattr(config, "VIDEO_FORMAT", "standard") == "split_screen":
            from app.ai_visuals import generate_ai_image, image_to_motion_clip
            from app.split_screen import fetch_satisfying_clip, render_split_screen_video
            import subprocess

            top_img = work_dir / "top_scene.jpg"
            top_clip = work_dir / "top_clip.mp4"
            top_prompt = (script_data.get("visual_prompts") or [topic])[0]
            generate_ai_image(top_prompt, top_img)
            image_to_motion_clip(top_img, top_clip, duration=6.0, motion_type="zoom_in")

            bottom_clip = work_dir / "bottom_satisfying.mp4"
            fetch_satisfying_clip(bottom_clip, api_key=config.PEXELS_API_KEY)

            stage_started = time.monotonic()
            render_split_screen_video(
                str(top_clip),
                str(bottom_clip),
                audio_path,
                subtitle_path,
                video_path,
                bgm_path=bgm_path,
                bgm_volume=0.18,
            )
            log_event(job_id, "split_screen_render_done", seconds=round(time.monotonic() - stage_started, 1))

            cmd_thumb = [
                "ffmpeg", "-y",
                "-ss", "00:00:03",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                thumbnail_path,
            ]
            subprocess.run(cmd_thumb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not Path(thumbnail_path).is_file():
                render_card(
                    script_data["title"],
                    brand_name=config.IMAGE_BRAND_NAME,
                    accent=config.IMAGE_ACCENT,
                    output_path=thumbnail_path,
                )
        else:
            stage_started = time.monotonic()
            # Sahne sayısı ses süresinden gelir — sabit 6/10 sahne, uzun anlatımda
            # görüntülerin başa sarılmasına (slayt hissine) yol açıyordu.
            try:
                audio_duration = get_audio_duration(audio_path)
            except Exception as dur_err:
                print(f"[pipeline] Ses süresi okunamadı ({dur_err}); 30 sn varsayıldı.")
                audio_duration = 30.0
            engine = str(getattr(config, "VISUAL_ENGINE", "stock") or "").lower()
            allow_stock = bool(getattr(config, "ALLOW_STOCK_FALLBACK", True))
            # Env flag only (not MagicMock-patched config) — default off preserves legacy tests.
            director_on = os.environ.get("DIRECTOR_ENABLED", "false").lower() == "true"
            stock_primary = engine == "stock" or director_on
            durations = plan_scene_schedule(
                audio_duration,
                base_duration=SCENE_CLIP_DURATION,
                xfade_duration=SCENE_XFADE_DURATION,
                max_scenes=STOCK_MAX_SCENES if stock_primary else None,
            )
            scene_count = min(len(durations), MAX_SCENES)
            durations = durations[:scene_count]
            log_event(
                job_id, "scene_plan",
                audio_seconds=round(audio_duration, 1),
                scene_count=scene_count,
                scene_durations=[round(d, 2) for d in durations],
            )

            visual_prompts = script_data.get("visual_prompts")
            visual_keywords = script_data.get("visual_keywords") or extract_keywords(
                script_data["script"]
            )
            concrete_nouns = script_data.get("concrete_nouns") or []
            visual_stats: dict = {}
            used_stock_clips = False
            if director_on:
                # New architecture behind flag. Model routing stays on AI router
                # (LLM_API_URL). Legacy VISUAL_ENGINE branch below is untouched when off.
                from app.director import plan_and_fetch_scenes

                used_stock_clips = True
                # Story consistency from script quality → director gate
                sq = script_data.get("script_quality") or {}
                visual_stats["story_consistency"] = sq.get("story_consistency") or {}
                if sq.get("story_consistency", {}).get("status") == "FAIL":
                    quality["review_required"] = True
                    quality["review_reason"] = quality.get("review_reason") or (
                        "story_consistency_fail"
                    )
                try:
                    clip_paths = plan_and_fetch_scenes(
                        scene_count=scene_count,
                        topic=topic,
                        script_data=script_data,
                        output_dir=str(work_dir),
                        state_path=str(media_dir / "used_clips.json"),
                        clip_duration=SCENE_CLIP_DURATION,
                        api_key=config.OPENROUTER_API_KEY,
                        stats_out=visual_stats,
                    )
                except (FalAuthBillingError, KlingAuthBillingError) as fal_exc:
                    _notify_fal_auth_billing_fail(job_id, fal_exc)
                    raise
                quality["engine"] = "director"
                # Phase 3.1: static top title OFF unless explicitly enabled + provided.
                hook_plan = visual_stats.get("hook_director") or {}
                punch = ""
                hook_title_on = bool(
                    getattr(config, "PHASE3_HOOK_TITLE_ENABLED", False)
                )
                if hook_title_on:
                    punch = str(hook_plan.get("overlay_text") or "").strip()
                hook_secs = float(hook_plan.get("hook_seconds") or 1.0)
                write_ass(
                    word_boundaries,
                    subtitle_path,
                    words_per_cue=2,
                    highlight=True,
                    add_emojis=getattr(config, "ENABLE_SUBTITLE_EMOJIS", False) is True,
                    hook_text=punch or None,
                    hook_seconds=min(hook_secs, 1.2) if punch else 0.0,
                    karaoke_start_seconds=0.0,
                    hook_max_words=4,
                    phase3=phase3_caps,
                    emphasis_words=narration_profile.emphasis if phase3_caps else None,
                )
                # Refresh pacing notes from Director beat roles (no visual rewrite).
                roles = []
                for b in visual_stats.get("word_to_visual") or []:
                    roles.append(str(b.get("narrative_role") or b.get("gate_reason") or ""))
                pacing_profile = build_pacing_profile(
                    script=script_data.get("script") or "",
                    beat_roles=roles,
                )
                quality["pacing_profile"] = pacing_profile.to_dict()
                quality["hook"] = hook_text
                quality["hook_director"] = {**(hook_plan or {}), "overlay_text": punch}
                quality["hook_overlay_duration"] = float(hook_secs) if punch else 0.0
                quality["word_to_visual"] = visual_stats.get("word_to_visual")
                quality["retention_events"] = visual_stats.get("retention_events") or []
                quality["person_retrieval"] = visual_stats.get("person_retrieval") or []
                quality["phase31"] = True
                quality["storyboard_before_retrieval"] = visual_stats.get(
                    "storyboard_before_retrieval"
                )
                quality["storyboard_coverage"] = visual_stats.get("storyboard_coverage")
                quality["visual_information_units"] = visual_stats.get(
                    "visual_information_units"
                )
                quality["no_slideshow_gate"] = visual_stats.get("no_slideshow_gate")
                quality["source_asset_stats"] = visual_stats.get("source_asset_stats")
                quality["shot_count"] = visual_stats.get("shot_count")
                quality["unique_source_asset_count"] = visual_stats.get(
                    "unique_source_asset_count"
                )
                quality["important_beat_coverage"] = visual_stats.get(
                    "important_beat_coverage"
                )
                quality["story_consistency"] = visual_stats.get(
                    "story_consistency"
                ) or sq.get("story_consistency")
                gate = visual_stats.get("no_slideshow_gate") or {}
                if gate.get("status") == "FAIL":
                    quality["review_required"] = True
                    quality["review_reason"] = "no_slideshow_gate_fail:" + ",".join(
                        gate.get("reasons") or []
                    )
                elif gate.get("status") == "REVIEW_REQUIRED":
                    quality["review_required"] = True
                    quality["review_reason"] = quality.get("review_reason") or (
                        "no_slideshow_gate_review:" + ",".join(gate.get("reasons") or [])
                    )
                log_event(
                    job_id, "director_clips_ready",
                    clip_count=len(clip_paths),
                    beat_count=visual_stats.get("beat_count"),
                    scene_relevance=visual_stats.get("scene_relevance"),
                    director_plan=visual_stats.get("director_plan"),
                    hook_director=quality["hook_director"],
                    word_to_visual=visual_stats.get("word_to_visual"),
                    retention_events=visual_stats.get("retention_events"),
                    person_retrieval=visual_stats.get("person_retrieval"),
                    stock_cache_reuse_ratio=visual_stats.get("stock_cache_reuse_ratio"),
                    ai_image_used=visual_stats.get("ai_image_used"),
                    no_slideshow_gate=gate,
                    shot_count=visual_stats.get("shot_count"),
                    unique_source_asset_count=visual_stats.get(
                        "unique_source_asset_count"
                    ),
                    important_beat_coverage=visual_stats.get("important_beat_coverage"),
                    seconds=round(time.monotonic() - stage_started, 1),
                )
                try:
                    sd_full = media_dir / f"SOURCE_DIVERSITY_TRACE_{job_id}.json"
                    prev = {}
                    if sd_full.is_file():
                        try:
                            prev = json.loads(sd_full.read_text(encoding="utf-8"))
                        except Exception:
                            prev = {}
                    prev.update(
                        {
                            "job_id": job_id,
                            "topic": topic,
                            "final_script": script_data.get("script"),
                            "shot_count": visual_stats.get("shot_count"),
                            "unique_source_asset_count": visual_stats.get(
                                "unique_source_asset_count"
                            ),
                            "source_asset_stats": visual_stats.get("source_asset_stats"),
                            "important_beat_coverage": visual_stats.get(
                                "important_beat_coverage"
                            ),
                            "beat_coverage": visual_stats.get("beat_coverage"),
                            "important_beat_retry": visual_stats.get(
                                "important_beat_retry"
                            ),
                            "beat_recovery": visual_stats.get("beat_recovery"),
                            "no_slideshow_gate": gate,
                            "story_consistency": quality.get("story_consistency")
                            or visual_stats.get("story_consistency"),
                            "storyboard_coverage": visual_stats.get(
                                "storyboard_coverage"
                            ),
                            "visual_information_units": visual_stats.get(
                                "visual_information_units"
                            ),
                            "word_to_visual": visual_stats.get("word_to_visual"),
                            "person_retrieval": visual_stats.get("person_retrieval"),
                        }
                    )
                    payload = json.dumps(prev, indent=2, ensure_ascii=False)[:500000]
                    sd_full.write_text(payload, encoding="utf-8")
                    # Also write uncovered-beat recovery trace alias
                    (media_dir / f"UNCOVERED_BEAT_RECOVERY_TRACE_{job_id}.json").write_text(
                        payload, encoding="utf-8"
                    )
                except Exception as sd_err:
                    print(f"[pipeline] source diversity trace update failed: {sd_err}", flush=True)
            elif visual_prompts and engine != "stock":
                from app.ai_video_engine import generate_video_scenes
                try:
                    clip_paths = generate_video_scenes(
                        visual_prompts,
                        output_dir=str(work_dir),
                        clip_duration=SCENE_CLIP_DURATION,
                        target_count=scene_count,
                        topic=topic,
                        visual_keywords=visual_keywords,
                        concrete_nouns=concrete_nouns,
                        stats_out=visual_stats,
                    )
                except (FalAuthBillingError, KlingAuthBillingError) as fal_exc:
                    _notify_fal_auth_billing_fail(job_id, fal_exc)
                    raise
                log_event(
                    job_id, "ai_clips_generated",
                    prompt_count=len(visual_prompts),
                    clip_count=len(clip_paths),
                    scene_relevance=visual_stats.get("scene_relevance"),
                    stock_cache_reuse_ratio=visual_stats.get("stock_cache_reuse_ratio"),
                    concrete_nouns=concrete_nouns,
                    seconds=round(time.monotonic() - stage_started, 1),
                )
            elif engine == "stock" or allow_stock:
                # Explicit stock engine OR gated fallback — still topic-anchored,
                # never silent unrelated luxury B-roll.
                used_stock_clips = True
                scene_queries = resolve_scene_queries(
                    scene_count=scene_count,
                    topic=topic,
                    script=script_data.get("script") or "",
                    scene_stock_queries=script_data.get("scene_stock_queries"),
                    visual_prompts=visual_prompts or [],
                    visual_keywords=visual_keywords,
                )
                clip_paths = fetch_stock_clips(
                    scene_queries,
                    count=scene_count,
                    api_key=config.PEXELS_API_KEY,
                    pixabay_api_key=getattr(config, "PIXABAY_API_KEY", ""),
                    enable_mixkit=getattr(config, "ENABLE_MIXKIT_STOCK", True),
                    output_dir=str(work_dir),
                    state_path=str(media_dir / "used_clips.json"),
                    topic=topic,
                    allow_used_id_reuse=False,
                    fallback_on_empty=False,
                    meta_out=visual_stats,
                )
                log_event(
                    job_id, "clips_fetched",
                    keywords=scene_queries,
                    scene_relevance=visual_stats.get("scene_relevance")
                    or [
                        {"scene": i, "source": "stock", "query": q}
                        for i, q in enumerate(scene_queries)
                    ],
                    stock_cache_reuse_ratio=visual_stats.get("stock_cache_reuse_ratio", 0.0),
                    providers=visual_stats.get("providers"),
                    clip_count=len(clip_paths),
                    seconds=round(time.monotonic() - stage_started, 1),
                )
            else:
                raise RuntimeError(
                    "No visual_prompts and stock disabled "
                    f"(VISUAL_ENGINE={engine}, ALLOW_STOCK_FALLBACK={allow_stock}). "
                    "Refusing silent Pexels fill."
                )

            if not clip_paths:
                raise RuntimeError(
                    f"No stock clips or visual clips could be generated for topic: {topic}"
                )

            stage_started = time.monotonic()
            sfx_path = None
            if config.ENABLE_SFX:
                from app.sfx import build_sfx_track
                try:
                    audio_cues = []
                    t_acc = 0.0
                    for b in (visual_stats.get("word_to_visual") or []):
                        dur = float(b.get("duration") or 0) or 0.0
                        cue = b.get("audio_cue") or b.get("emphasis_cue")
                        if cue and str(cue).lower() not in ("", "none", "null"):
                            audio_cues.append({"t": t_acc + max(dur * 0.15, 0.05), "kind": cue})
                        t_acc += dur
                    sfx_path = build_sfx_track(
                        audio_duration,
                        clip_duration=SCENE_CLIP_DURATION,
                        output_path=str(work_dir / "sfx.wav"),
                        sfx_dir=str(work_dir),
                        transition_times=scene_transition_times(
                            durations, SCENE_XFADE_DURATION
                        ),
                        word_boundaries=word_boundaries,
                        phase3=phase3_ret,
                        audio_cues=audio_cues if phase3_ret else None,
                    )
                    quality["sfx_cues"] = len(audio_cues)
                except Exception as sfx_err:
                    log_event(job_id, "sfx_failed", error=str(sfx_err))

            # Değişken ritimli kurgu: kanca hızlı, anlatı nefes alır.
            render_stats: dict = {}
            render_video(
                clip_paths,
                audio_path,
                subtitle_path,
                video_path,
                str(work_dir),
                clip_duration=SCENE_CLIP_DURATION,
                xfade_duration=SCENE_XFADE_DURATION,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                cinematic_grade=config.CINEMATIC_GRADE,
                sfx_path=sfx_path,
                # Stock mp4 already has camera motion. Live scale-KenBurns + many
                # xfade inputs stalls ffmpeg (frame=0). Keep native motion + xfade.
                # Still-image / Flux path applies Ken Burns inside ai_visuals instead.
                apply_zoompan=False,
                stats_out=render_stats,
                duck_bgm=phase3_music,
                duck_threshold=float(music_profile.duck_threshold),
                duck_ratio=float(music_profile.duck_ratio),
                loudnorm=phase3_audio,
            )
            log_event(
                job_id, "render_done",
                seconds=round(time.monotonic() - stage_started, 1),
                **render_stats,
            )

            # Kalite kapısı: aşırı tekrar = slayt gösterisi. Sessizce yayınlama,
            # gürültü çıkar (mevcut felsefe: sessiz bozulma yok).
            reuse = render_stats.get("clip_reuse_ratio", 0.0)
            stock_cache_reuse = float(visual_stats.get("stock_cache_reuse_ratio") or 0.0)
            quality.update(
                {
                    "scene_count": int(render_stats.get("scene_count", 0)),
                    "clip_count": int(render_stats.get("clip_count", len(clip_paths))),
                    "clip_reuse_ratio": float(reuse),
                    "stock_cache_reuse_ratio": stock_cache_reuse,
                    "scene_relevance": visual_stats.get("scene_relevance")
                    or [
                        {"scene": i, "query": q}
                        for i, q in enumerate(visual_stats.get("queries") or [])
                    ],
                    "hook": hook_text,
                    "tts": tts_provider,
                    "engine": quality.get("engine")
                    or str(getattr(config, "VISUAL_ENGINE", "unknown")),
                }
            )
            # Hard fail: too many clips pulled from used_clips cache = topic drift.
            if stock_cache_reuse > MAX_STOCK_CACHE_REUSE_RATIO:
                quality["warning"] = "stock_cache_reuse_high"
                log_event(
                    job_id, "quality_warning",
                    reason="stock_cache_reuse_high",
                    stock_cache_reuse_ratio=stock_cache_reuse,
                    threshold=MAX_STOCK_CACHE_REUSE_RATIO,
                    scene_relevance=quality.get("scene_relevance"),
                )
                raise RuntimeError(
                    f"stock_cache_reuse_ratio {stock_cache_reuse} exceeds "
                    f"{MAX_STOCK_CACHE_REUSE_RATIO} — refusing unrelated clip reuse. "
                    "Clear used_clips.json or retry so fresh topic-matched footage can load."
                )
            # Within-video slideshow gate (scenes / unique clips).
            if reuse > MAX_CLIP_REUSE_RATIO:
                quality["warning"] = "clip_reuse_ratio_high"
                log_event(
                    job_id, "quality_warning",
                    reason="clip_reuse_ratio_high",
                    clip_reuse_ratio=reuse,
                    threshold=MAX_CLIP_REUSE_RATIO,
                )
                print(
                    f"[pipeline] UYARI: görüntü tekrar oranı {reuse}x "
                    f"(eşik {MAX_CLIP_REUSE_RATIO}x). Video slayt hissi verebilir.",
                    flush=True,
                )
            elif tts_provider == "edge":
                quality["warning"] = "tts_edge_fallback"

            # YouTube'a özel kapak
            import subprocess
            cmd_thumb = [
                "ffmpeg", "-y",
                "-ss", "00:00:03",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                thumbnail_path,
            ]
            subprocess.run(cmd_thumb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not Path(thumbnail_path).is_file():
                render_card(
                    script_data["title"],
                    brand_name=config.IMAGE_BRAND_NAME,
                    accent=config.IMAGE_ACCENT,
                    output_path=thumbnail_path,
                )

        # Dual-Format: TikTok & Instagram Reels için hipnotik Split-Screen varyantı üret
        split_screen_filename = video_filename
        if getattr(config, "VIDEO_FORMAT", "standard") != "split_screen":
            split_screen_filename = f"{job_id}_splitscreen.mp4"
            split_screen_path = str(media_dir / split_screen_filename)
            try:
                from app.split_screen import fetch_satisfying_clip, render_split_screen_video
                bottom_clip = work_dir / "bottom_satisfying.mp4"
                fetch_satisfying_clip(bottom_clip, api_key=config.PEXELS_API_KEY)
                top_source = clip_paths[0] if clip_paths else video_path
                render_split_screen_video(
                    top_clip_path=str(top_source),
                    bottom_clip_path=str(bottom_clip),
                    audio_path=audio_path,
                    sub_path=subtitle_path,
                    output_path=split_screen_path,
                    bgm_path=bgm_path,
                    bgm_volume=0.18,
                )
            except Exception as ss_err:
                print(f"[pipeline] Split-screen üretilemedi ({ss_err}); cinematic kullanılacak.", flush=True)
                split_screen_path = video_path
                split_screen_filename = video_filename
        else:
            split_screen_path = video_path

        result = {
            "job_id": job_id,
            "video_path": video_path,
            "video_filename": video_filename,
            "split_screen_path": split_screen_path,
            "split_screen_filename": split_screen_filename,
            "thumbnail_path": thumbnail_path,
            "topic": topic,
            "title": script_data["title"],
            "description": script_data["description"],
            "tags": script_data["tags"],
            "pinned_comment": script_data.get("pinned_comment", ""),
            "script": script_data.get("script") or "",
            "raw_script": script_data.get("raw_script") or raw_before_quality,
            "final_script": script_data.get("final_script") or script_data.get("script") or "",
            "quality": quality,
        }
        job_store.update_job(
            media_dir,
            job_id,
            state="awaiting_approval",
            title=script_data["title"],
            topic=topic,
            payload=result,
            error="",
        )
        job_store.write_pending_mirror(media_dir, result)
        # Stage A: joinable ProductionManifest (no behavioral change).
        try:
            from app.documentary_v2 import emit_legacy_job_manifest

            emit_legacy_job_manifest(
                media_dir=media_dir,
                job_id=job_id,
                topic=topic or "",
                script_data=script_data,
                quality=quality,
                result=result,
                audio_duration=locals().get("audio_duration"),
            )
        except Exception as _manifest_err:
            print(f"[pipeline] Stage A manifest skipped: {_manifest_err}", flush=True)
        # Human gate: send approve/reject even when caller is curl /generate
        # (n8n also sendVideo — duplicate OK; never auto-publish).
        _notify_telegram_awaiting_approval(result)
        log_event(
            job_id,
            "generate_complete",
            total_seconds=round(time.monotonic() - started_at, 1),
            hook=quality.get("hook"),
            clip_reuse_ratio=quality.get("clip_reuse_ratio"),
            stock_cache_reuse_ratio=quality.get("stock_cache_reuse_ratio"),
            scene_relevance=quality.get("scene_relevance"),
            tts=quality.get("tts"),
            engine=quality.get("engine"),
            quality_warning=quality.get("warning"),
        )
        return result
    except (FalAuthBillingError, KlingAuthBillingError):
        # Already logged + Telegram'd via _notify_fal_auth_billing_fail.
        try:
            job_store.mark_failed(media_dir, job_id, "fal_auth_or_billing")
        except Exception:
            pass
        if from_pool and topic:
            release_topic(topic, state_path)
        raise
    except Exception as exc:
        log_event(
            job_id, "generate_failed",
            error=str(exc),
            total_seconds=round(time.monotonic() - started_at, 1),
        )
        try:
            job_store.mark_failed(media_dir, job_id, str(exc))
        except Exception:
            pass
        # Başarısız üretim konuyu yakmasın — havuza geri bırak,
        # ertesi gün (veya bir sonraki denemede) tekrar seçilebilsin.
        if from_pool and topic:
            release_topic(topic, state_path)
        raise
    finally:
        # Runs on both success and failure so a render/API error never leaves
        # half-downloaded clips or TTS audio behind on disk.
        shutil.rmtree(work_dir, ignore_errors=True)
