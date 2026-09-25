"""EDL-driven FFmpeg assembly — executes EditDecisionList, does not invent shots."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from app.documentary_v2.schemas import EditDecision, EditDecisionList, RenderManifest
from app.render import (
    FPS,
    HEIGHT,
    WIDTH,
    _escape_for_filter,
    _normalize_filter,
    _zoompan_filter,
    get_audio_duration,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def _subtle_still_filter(duration: float) -> str:
    """Tasteful slow push — presentation only, not fake VIU diversity."""
    d = max(float(duration), 0.5)
    zoom_max = 0.04  # gentler than legacy Ken Burns
    zoom_step = zoom_max / (d * FPS)
    return (
        f"zoompan=z='min(zoom+{zoom_step:.6f},{1 + zoom_max})':"
        f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={WIDTH}x{HEIGHT}:fps={FPS}"
    )


def render_from_edl(
    edl: EditDecisionList,
    *,
    audio_path: str,
    caption_path: str,
    output_path: str,
    work_dir: str,
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
    duck_bgm: bool = True,
    loudnorm: bool = True,
    cinematic_grade: bool = False,
    render_timeout_sec: float = 240.0,
) -> RenderManifest:
    """Assemble vertical MP4 from EDL. Default transition = cut (xfade=0)."""
    decisions = [d for d in edl.decisions if d.local_path and Path(d.local_path).is_file()]
    if not decisions:
        raise ValueError("EDL has no renderable decisions")
    cursor = 0.0
    for dec in decisions:
        if abs(float(dec.start_time) - cursor) > 0.05:
            raise ValueError(f"edl_timeline_gap:{cursor:.3f}->{dec.start_time:.3f}")
        if float(dec.end_time) <= float(dec.start_time):
            raise ValueError(f"edl_invalid_duration:{dec.edit_id}")
        cursor = float(dec.end_time)

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    audio_duration = get_audio_duration(audio_path)
    durations = [float(d.end_time - d.start_time) for d in decisions]
    timeline_duration = cursor
    output_duration = max(timeline_duration, float(audio_duration))
    normalize = _normalize_filter()

    inputs: list[str] = []
    filter_parts: list[str] = []
    labels: list[str] = []

    for i, (dec, scene_duration) in enumerate(zip(decisions, durations)):
        clip = dec.local_path
        is_image = _is_image(clip)
        if is_image:
            inputs += ["-loop", "1", "-i", clip]
        else:
            ss = float(dec.source_in or 0.0)
            if ss > 0:
                inputs += ["-stream_loop", "-1", "-ss", f"{ss:.2f}", "-i", clip]
            else:
                inputs += ["-stream_loop", "-1", "-i", clip]

        label = f"[v{i}]"
        tail = f"trim=duration={scene_duration:.3f},setpts=PTS-STARTPTS,fps={FPS}"
        policy = (dec.motion_policy or "preserve_native").lower()
        if is_image and policy in {"subtle_push", "subtle_pan"}:
            chain = f"[{i}:v]{normalize},{_subtle_still_filter(scene_duration)},{tail}"
        elif is_image:
            # Hold still with no aggressive zoom
            chain = f"[{i}:v]{normalize},fps={FPS},{tail}"
        else:
            # Preserve native motion — no live Ken Burns (no fake variety)
            chain = f"[{i}:v]{normalize},{tail}"
        filter_parts.append(f"{chain},format=yuv420p{label}")
        labels.append(f"v{i}")

    # Clean cuts: concat (not xfade spam)
    if len(labels) == 1:
        filter_parts.append(f"[{labels[0]}]null[vout]")
    else:
        n = len(labels)
        concat_in = "".join(f"[{lab}]" for lab in labels)
        filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")

    escaped_srt = _escape_for_filter(caption_path)
    tail_pad = max(0.0, output_duration - timeline_duration)
    filter_parts.append(
        f"[vout]tpad=stop_mode=clone:stop_duration={tail_pad + 0.05:.3f},"
        f"trim=duration={output_duration:.3f},fps={FPS},"
        f"subtitles='{escaped_srt}'[vfinal]"
    )

    video_input_count = len(decisions)
    inputs += ["-i", audio_path]
    has_bgm = bool(bgm_path and Path(bgm_path).is_file())
    next_audio_idx = video_input_count + 1
    bgm_idx = None
    if has_bgm:
        inputs += ["-i", bgm_path]
        bgm_idx = next_audio_idx

    nar = f"[{video_input_count}:a]"
    if has_bgm and bgm_idx is not None:
        if duck_bgm:
            filter_parts.append(f"{nar}asplit=2[speechdry][speechsc]")
            filter_parts.append(
                f"[{bgm_idx}:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgmraw]"
            )
            filter_parts.append(
                "[bgmraw][speechsc]sidechaincompress="
                "threshold=0.02:ratio=6:attack=40:release=280:"
                "makeup=1:knee=2.5[bgmduck]"
            )
            filter_parts.append(
                "[speechdry][bgmduck]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[amixed]"
            )
        else:
            filter_parts.append(
                f"[{bgm_idx}:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
                f"{nar}[bgm]amix=inputs=2:duration=first:dropout_transition=2[amixed]"
            )
        if loudnorm:
            filter_parts.append(
                "[amixed]loudnorm=I=-14:TP=-1.5:LRA=11:print_format=summary,"
                "alimiter=limit=0.55:level=false[afinal]"
            )
        else:
            filter_parts.append("[amixed]anull[afinal]")
        audio_map = ["-map", "[afinal]"]
    else:
        if loudnorm:
            filter_parts.append(
                f"{nar}loudnorm=I=-14:TP=-1.5:LRA=11:print_format=summary,"
                "alimiter=limit=0.55:level=false[afinal]"
            )
            audio_map = ["-map", "[afinal]"]
        else:
            audio_map = ["-map", f"{video_input_count}:a:0"]

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]", *audio_map,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-t", f"{output_duration:.3f}",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=render_timeout_sec)
    if result.returncode != 0:
        raise RuntimeError(f"edl_ffmpeg_failed:{(result.stderr or '')[-2000:]}")

    return RenderManifest(
        render_id=f"rm:{uuid.uuid4().hex[:12]}",
        job_id=edl.job_id,
        video_id=edl.video_id,
        output_path=str(output_path),
        resolution=f"{WIDTH}x{HEIGHT}",
        fps=float(FPS),
        duration_sec=round(output_duration, 3),
        edl_id=edl.edl_id,
        edl=edl.to_dict(),
        audio_narration_path=audio_path,
        audio_bgm_path=bgm_path or "",
        caption_path=caption_path,
        asset_paths=[d.local_path for d in decisions],
        duck_bgm=bool(duck_bgm and has_bgm),
        loudnorm=loudnorm,
        bgm_volume=float(bgm_volume) if has_bgm else 0.0,
        transitions=["cut"] * len(decisions),
        vocals_verified=True,
    )
