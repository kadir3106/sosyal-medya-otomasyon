"""Technical render QA — must pass before creative critic."""
from __future__ import annotations

import json
import re
import tempfile
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image


@dataclass
class TechnicalQAResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_sec: float | None = None
    has_video: bool = False
    has_audio: bool = False
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def probe_media(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json", path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe_failed:{r.stderr[-400:]}")
    return json.loads(r.stdout or "{}")


def _freeze_diagnostics(path: str, duration_sec: float) -> dict:
    fps = 2.0
    width, height = 32, 18
    with tempfile.TemporaryDirectory(prefix="freeze_probe_") as temp_dir:
        pattern = str(Path(temp_dir) / "frame_%04d.png")
        probe = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", path, "-an",
                "-r", f"{fps:g}", "-s", f"{width}x{height}", pattern,
            ],
            capture_output=True,
        )
        frames = [
            Image.open(frame_path).convert("L").tobytes()
            for frame_path in sorted(Path(temp_dir).glob("frame_*.png"))
        ]
    frame_size = width * height
    intervals: list[tuple[float, float]] = []
    run_start: float | None = None
    for index in range(1, len(frames)):
        diff = sum(abs(a - b) for a, b in zip(frames[index - 1], frames[index])) / frame_size
        if diff <= 1.0:
            if run_start is None:
                run_start = (index - 1) / fps
        elif run_start is not None:
            intervals.append((run_start, index / fps))
            run_start = None
    if run_start is not None:
        intervals.append((run_start, float(duration_sec)))
    longest = max((end - start for start, end in intervals), default=0.0)
    tail = max(
        (end - start for start, end in intervals if end >= float(duration_sec) - 0.15),
        default=0.0,
    )
    return {
        "freeze_intervals": [
            {"start_sec": round(start, 3), "end_sec": round(end, 3)}
            for start, end in intervals
        ],
        "longest_freeze_sec": round(longest, 3),
        "tail_freeze_sec": round(tail, 3),
        "freeze_probe_ok": probe.returncode == 0 and len(frames) >= 2,
        "freeze_sample_fps": fps,
    }


def technical_qa(
    video_path: str,
    *,
    expected_duration: float | None = None,
    expected_width: int = 1080,
    expected_height: int = 1920,
    duration_tol: float = 1.5,
) -> TechnicalQAResult:
    p = Path(video_path)
    if not p.is_file() or p.stat().st_size < 1000:
        return TechnicalQAResult(ok=False, reasons=["missing_or_tiny_file"])
    try:
        data = probe_media(str(p))
    except Exception as exc:
        return TechnicalQAResult(ok=False, reasons=[f"probe_error:{exc}"])

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]
    reasons: list[str] = []
    if not vstreams:
        reasons.append("no_video_stream")
    if not astreams:
        reasons.append("no_audio_stream")
    vs = vstreams[0] if vstreams else {}
    w = int(vs.get("width") or 0)
    h = int(vs.get("height") or 0)
    if w != expected_width or h != expected_height:
        reasons.append(f"dimension_mismatch:{w}x{h}")
    # fps
    fps = None
    rate = vs.get("avg_frame_rate") or vs.get("r_frame_rate") or "0/0"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else None
    except Exception:
        fps = None
    dur = float(fmt.get("duration") or 0)
    video_dur = float(vs.get("duration") or 0) if vs else 0.0
    audio_dur = float(astreams[0].get("duration") or 0) if astreams else 0.0
    if video_dur and audio_dur and abs(video_dur - audio_dur) > 0.15:
        reasons.append(
            f"stream_duration_mismatch:video={video_dur:.2f}:audio={audio_dur:.2f}"
        )
    if expected_duration is not None and abs(dur - expected_duration) > duration_tol:
        reasons.append(f"duration_mismatch:got={dur:.2f}:exp={expected_duration:.2f}")
    if dur < 1.0:
        reasons.append("duration_too_short")
    true_peak = None
    if astreams:
        peak_probe = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-vn",
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        matches = re.findall(r"Peak:\s*([-+]?\d+(?:\.\d+)?)\s*dBFS", peak_probe.stderr)
        if peak_probe.returncode or not matches:
            reasons.append("audio_peak_probe_failed")
        else:
            true_peak = float(matches[-1])
            if true_peak > -1.0:
                reasons.append(f"audio_true_peak_high:{true_peak:.1f}dBFS")

    freeze = _freeze_diagnostics(str(p), dur) if vstreams and dur > 0 else {
        "freeze_intervals": [], "longest_freeze_sec": 0.0,
        "tail_freeze_sec": 0.0, "freeze_probe_ok": False,
    }
    return TechnicalQAResult(
        ok=not reasons,
        reasons=reasons,
        width=w or None,
        height=h or None,
        fps=fps,
        duration_sec=dur,
        has_video=bool(vstreams),
        has_audio=bool(astreams),
        details={"format": fmt.get("format_name"), "size": p.stat().st_size,
                 "video_duration_sec": video_dur, "audio_duration_sec": audio_dur,
                 "audio_true_peak_dbfs": true_peak, **freeze},
    )
