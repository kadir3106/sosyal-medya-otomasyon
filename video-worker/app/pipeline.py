import asyncio
import json
import shutil
import time
from pathlib import Path

from app.audio_bgm import get_or_create_bgm
from app.config import config
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
from app.stock_media import extract_keywords, fetch_stock_clips
from app.subtitles import write_ass
from app.topics import release_topic, select_next_topic
from app.tts import synthesize_speech

# Sahne süresi/geçiş süresi — render.py ile AYNI değerler kullanılmalı.
SCENE_CLIP_DURATION = 2.2
SCENE_XFADE_DURATION = 0.4

# Sahne sayısı artık sabit değil: ses süresinden hesaplanır (bkz. plan_scene_schedule).
# Bu yalnızca emniyet tavanı — 90 sn'lik ses bile bu sayının altında kalır.
MAX_SCENES = 40

# Tekrar oranı bu eşiği aşarsa video "slayt gösterisi" hissi verir; sessizce
# yayınlanmasındansa gürültü çıkarması daha iyidir.
MAX_CLIP_REUSE_RATIO = 1.35


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
    topics_path = config.TOPICS_PATH_TR if lang == "tr" else config.TOPICS_PATH
    voice = config.VIDEO_VOICE or ("tr-TR-EmelNeural" if lang == "tr" else "en-US-GuyNeural")

    started_at = time.monotonic()
    from_pool = topic is None
    try:
        job_store.create_job(
            media_dir, job_id, kind="video", state="generating", topic=topic
        )
        if from_pool:
            topic = select_next_topic(topics_path, state_path)
            job_store.update_job(media_dir, job_id, topic=topic)
        log_event(job_id, "topic_selected", topic=topic, lang=lang)

        stage_started = time.monotonic()
        winning_context = None
        if config.ENABLE_ANALYTICS_MEMORY:
            try:
                from app.channel_growth import get_winning_context_for_prompt
                winning_context = get_winning_context_for_prompt()
            except Exception:
                pass

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
            seconds=round(time.monotonic() - stage_started, 1),
        )

        audio_path = str(work_dir / "speech.mp3")
        stage_started = time.monotonic()
        # synthesize_speech is async; we're already in a worker thread so
        # asyncio.run is safe (no running loop in this thread).
        tts_meta: dict = {}
        word_boundaries = asyncio.run(
            synthesize_speech(
                script_data["script"],
                audio_path,
                voice=voice,
                rate=config.VIDEO_VOICE_RATE,
                meta_out=tts_meta,
            )
        )
        tts_provider = tts_meta.get("provider") or "unknown"
        log_event(
            job_id, "tts_done",
            word_count=len(word_boundaries),
            tts=tts_provider,
            edge_reason=tts_meta.get("edge_reason"),
            seconds=round(time.monotonic() - stage_started, 1),
        )

        # TikTok / Reels tarzı dinamik kelime vurgulamalı altyazı
        subtitle_path = write_ass(
            word_boundaries,
            str(work_dir / "subs.ass"),
            words_per_cue=2,
            highlight=True,
            add_emojis=getattr(config, "ENABLE_SUBTITLE_EMOJIS", False) is True,
        )

        hook_text = _extract_hook(script_data["script"])
        # Kalite telemetrisi (hook / TTS / motor) — Telegram + pending.json.
        quality: dict = {
            "hook": hook_text,
            "tts": tts_provider,
            "engine": str(getattr(config, "VISUAL_ENGINE", "unknown")),
        }
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
        bgm_path = get_or_create_bgm(bgm_dir)

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
            durations = plan_scene_schedule(
                audio_duration,
                base_duration=SCENE_CLIP_DURATION,
                xfade_duration=SCENE_XFADE_DURATION,
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
            if visual_prompts and config.VISUAL_ENGINE != "stock":
                from app.ai_video_engine import generate_video_scenes
                clip_paths = generate_video_scenes(
                    visual_prompts,
                    output_dir=str(work_dir),
                    clip_duration=SCENE_CLIP_DURATION,
                    target_count=scene_count,
                )
                log_event(
                    job_id, "ai_clips_generated",
                    prompt_count=len(visual_prompts),
                    clip_count=len(clip_paths),
                    seconds=round(time.monotonic() - stage_started, 1),
                )
            else:
                keywords = script_data.get("visual_keywords") or extract_keywords(script_data["script"])
                clip_paths = fetch_stock_clips(
                    keywords,
                    count=scene_count,
                    api_key=config.PEXELS_API_KEY,
                    output_dir=str(work_dir),
                    state_path=str(media_dir / "used_clips.json"),
                )
                log_event(
                    job_id, "clips_fetched",
                    keywords=keywords,
                    clip_count=len(clip_paths),
                    seconds=round(time.monotonic() - stage_started, 1),
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
                    # SFX, render'ın GERÇEK geçiş anlarına ve kelime zaman damgalarına oturtulur
                    sfx_path = build_sfx_track(
                        audio_duration,
                        clip_duration=SCENE_CLIP_DURATION,
                        output_path=str(work_dir / "sfx.wav"),
                        sfx_dir=str(work_dir),
                        transition_times=scene_transition_times(
                            durations, SCENE_XFADE_DURATION
                        ),
                        word_boundaries=word_boundaries,
                    )
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
                bgm_volume=0.15,
                cinematic_grade=config.CINEMATIC_GRADE,
                sfx_path=sfx_path,
                apply_zoompan=False,
                stats_out=render_stats,
            )
            log_event(
                job_id, "render_done",
                seconds=round(time.monotonic() - stage_started, 1),
                **render_stats,
            )

            # Kalite kapısı: aşırı tekrar = slayt gösterisi. Sessizce yayınlama,
            # gürültü çıkar (mevcut felsefe: sessiz bozulma yok).
            reuse = render_stats.get("clip_reuse_ratio", 0.0)
            quality.update(
                {
                    "scene_count": int(render_stats.get("scene_count", 0)),
                    "clip_count": int(render_stats.get("clip_count", len(clip_paths))),
                    "clip_reuse_ratio": float(reuse),
                    "hook": hook_text,
                    "tts": tts_provider,
                    "engine": str(getattr(config, "VISUAL_ENGINE", "unknown")),
                }
            )
            # Reuse high overrides softer TTS note so Telegram shows the worse gate.
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
        log_event(
            job_id,
            "generate_complete",
            total_seconds=round(time.monotonic() - started_at, 1),
            hook=quality.get("hook"),
            clip_reuse_ratio=quality.get("clip_reuse_ratio"),
            tts=quality.get("tts"),
            engine=quality.get("engine"),
            quality_warning=quality.get("warning"),
        )
        return result
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
