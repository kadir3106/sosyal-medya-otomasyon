"""Video temporal sampler — uniform + scene-change aware; not first/middle only."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.documentary_v2.providers.dedup import binary_hash
from app.documentary_v2.schemas import PreviewFrame, VisualPreviewBundle
from app.documentary_v2.verifier.frame_dedup import dedupe_frames, hash_frame_file


def _ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0:
            return None
        data = json.loads(out.stdout or "{}")
        dur = (data.get("format") or {}).get("duration")
        if dur is not None:
            return float(dur)
        for s in data.get("streams") or []:
            if s.get("duration"):
                return float(s["duration"])
    except Exception:
        return None
    return None


def _ffprobe_dims(path: Path) -> tuple[int | None, int | None]:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        streams = (json.loads(out.stdout or "{}").get("streams") or [{}])
        w = streams[0].get("width")
        h = streams[0].get("height")
        return (int(w) if w else None, int(h) if h else None)
    except Exception:
        return None, None


def uniform_timestamps(duration: float, count: int) -> list[float]:
    if duration <= 0 or count <= 0:
        return [0.0]
    if count == 1:
        return [max(0.0, duration * 0.5)]
    # Avoid exact 0 and exact end (decoder edge cases)
    eps = min(0.05, duration * 0.01)
    return [
        max(eps, min(duration - eps, duration * i / (count - 1)))
        for i in range(count)
    ]


def scene_change_timestamps(
    path: Path,
    *,
    threshold: float = 0.35,
    max_points: int = 6,
) -> list[float]:
    """FFmpeg scene detect — best-effort; empty on failure."""
    if not shutil.which("ffmpeg"):
        return []
    try:
        # showinfo prints pts_time on scene cuts
        cmd = [
            "ffmpeg",
            "-i",
            str(path),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        times: list[float] = []
        for line in (proc.stderr or "").splitlines():
            if "pts_time:" in line:
                try:
                    part = line.split("pts_time:")[1].split()[0]
                    times.append(float(part))
                except Exception:
                    continue
        # Dedup close scene points
        out: list[float] = []
        for t in times:
            if not out or abs(t - out[-1]) > 0.25:
                out.append(t)
            if len(out) >= max_points:
                break
        return out
    except Exception:
        return []


def extract_frame(path: Path, timestamp: float, dest: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(dest),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def estimate_motion_class(
    frames: list[PreviewFrame],
    *,
    duration: float | None,
) -> str:
    """Cheap motion estimate from frame hash variance — not semantic motion."""
    hashes = [f.perceptual_hash for f in frames if f.perceptual_hash]
    if len(hashes) < 2:
        return "STATIC_VIDEO" if (duration or 0) > 0 else "UNKNOWN_MOTION"
    diffs = []
    for i in range(1, len(hashes)):
        d = __import__(
            "app.documentary_v2.providers.dedup", fromlist=["hamming"]
        ).hamming(hashes[i - 1], hashes[i])
        if d is not None:
            diffs.append(d)
    if not diffs:
        return "UNKNOWN_MOTION"
    avg = sum(diffs) / len(diffs)
    if avg <= 2:
        return "STATIC_VIDEO"
    if avg <= 6:
        return "MINIMAL_CAMERA_MOTION"
    if avg <= 16:
        return "NATURAL_SUBJECT_MOTION"
    return "FAST_MONTAGE"


class VideoPreviewSampler:
    def __init__(self, max_frames: int = 7) -> None:
        self.max_frames = max(3, int(max_frames))

    def sample_video(
        self,
        media_path: Path | str,
        *,
        candidate_id: str,
        work_dir: Path | str | None = None,
    ) -> VisualPreviewBundle:
        path = Path(media_path)
        work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="vv_sample_"))
        frames_dir = work / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        duration = _ffprobe_duration(path) or 0.0
        width, height = _ffprobe_dims(path)

        # Cap analysis window — long archive dumps must not block Stage F VLM
        analysis_dur = duration
        if duration > 24.0:
            analysis_dur = 20.0

        if analysis_dur <= 3:
            n_uniform = min(5, self.max_frames)
        elif analysis_dur <= 12:
            n_uniform = min(7, self.max_frames)
        else:
            n_uniform = self.max_frames

        uniform = uniform_timestamps(analysis_dur or 1.0, n_uniform)
        # Scene detect only on short clips — full-file scene scan on 5–30min IA dumps hangs
        scenes: list[float] = []
        if duration > 0 and duration <= 45.0:
            scenes = scene_change_timestamps(path, max_points=max(2, self.max_frames // 2))
            scenes = [t for t in scenes if t <= analysis_dur]
        # Merge timestamps
        merged: list[tuple[float, str]] = [(t, "uniform") for t in uniform]
        for t in scenes:
            if all(abs(t - u) > 0.2 for u, _ in merged):
                merged.append((t, "scene_change"))
        merged.sort(key=lambda x: x[0])
        # Cap
        if len(merged) > self.max_frames:
            # Prefer keep first, last, and evenly spaced including scene marks
            step = max(1, len(merged) // self.max_frames)
            picked = merged[::step][: self.max_frames]
            if merged[-1] not in picked:
                picked[-1] = merged[-1]
            merged = picked

        frames: list[PreviewFrame] = []
        for i, (ts, src) in enumerate(merged):
            dest = frames_dir / f"f_{i:02d}_{ts:.2f}.jpg"
            ok = extract_frame(path, ts, dest)
            if not ok:
                continue
            try:
                ph = hash_frame_file(dest)
            except Exception:
                ph = ""
            frames.append(
                PreviewFrame(
                    timestamp_sec=ts, path=str(dest), perceptual_hash=ph, source=src
                )
            )

        frames = dedupe_frames(frames)
        try:
            fp = binary_hash(path)
        except Exception:
            fp = ""

        return VisualPreviewBundle(
            candidate_id=candidate_id,
            media_kind="video",
            duration_sec=duration or None,
            width=width,
            height=height,
            frames=frames,
            content_fingerprint=fp,
            technical={
                "motion_estimate": estimate_motion_class(frames, duration=duration),
                "sampler": "uniform+scene",
                "requested_max_frames": self.max_frames,
            },
        )

    def sample_image(
        self,
        media_path: Path | str,
        *,
        candidate_id: str,
    ) -> VisualPreviewBundle:
        path = Path(media_path)
        w = h = None
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            pass
        ph = ""
        try:
            ph = hash_frame_file(path)
        except Exception:
            pass
        try:
            fp = binary_hash(path)
        except Exception:
            fp = ""
        return VisualPreviewBundle(
            candidate_id=candidate_id,
            media_kind="image",
            duration_sec=None,
            width=w,
            height=h,
            frames=[
                PreviewFrame(
                    timestamp_sec=0.0,
                    path=str(path),
                    perceptual_hash=ph,
                    source="thumbnail",
                )
            ],
            content_fingerprint=fp,
            technical={"motion_estimate": "STATIC_VIDEO"},
        )


def build_preview_bundle(
    media_path: Path | str,
    *,
    candidate_id: str,
    media_kind: str = "",
    max_frames: int = 7,
    work_dir: Path | str | None = None,
) -> VisualPreviewBundle:
    path = Path(media_path)
    kind = media_kind
    if not kind:
        kind = "video" if path.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"} else "image"
    sampler = VideoPreviewSampler(max_frames=max_frames)
    if kind == "video":
        return sampler.sample_video(path, candidate_id=candidate_id, work_dir=work_dir)
    return sampler.sample_image(path, candidate_id=candidate_id)
