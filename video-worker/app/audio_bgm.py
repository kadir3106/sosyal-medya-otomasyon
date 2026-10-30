"""Phase 3 / 3.2 — BGM selection with strict no-vocal enforcement."""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

from app.phase3_profiles import (
    looks_instrumental_track,
    looks_vocal_track,
    mood_instrumental_hints,
    read_audio_tags,
    track_has_vocal_metadata,
)


def get_or_create_bgm(
    bgm_dir: str,
    duration_seconds: float = 60.0,
    *,
    vocals_allowed: bool = True,
    prefer_instrumental: bool = False,
    mood: str = "",
    allow_silence: bool = True,
    selection_out: dict | None = None,
) -> str | None:
    """Pick BGM. When vocals_allowed=False, never pick ambiguous/vocal tracks.

    Priority when vocals forbidden:
      1) verified instrumental matching mood
      2) verified instrumental ambient/cinematic
      3) synthetic default_ambient (generated, no vocals)
      4) None (silence) — preferred over wrong vocal music
    """
    path = Path(bgm_dir)
    path.mkdir(parents=True, exist_ok=True)

    tracks = [t for t in list(path.glob("*.mp3")) + list(path.glob("*.wav")) if t.is_file()]
    reason = "none"
    chosen: Path | None = None

    if vocals_allowed and not prefer_instrumental:
        if tracks:
            chosen = random.choice(tracks)
            reason = "legacy_any_track"
    else:
        # Strict documentary path: reject vocals + ambiguous.
        safe: list[Path] = []
        rejected: list[dict] = []
        for t in tracks:
            tags = read_audio_tags(t)
            vocalish = looks_vocal_track(t.name) or track_has_vocal_metadata(tags)
            instrumental = looks_instrumental_track(t.name) or _is_synthetic_ambient(t, tags)
            if vocalish:
                rejected.append({"file": t.name, "reason": "vocal_signal"})
                continue
            if not instrumental:
                # Ambiguous — for narrated docs, reject rather than risk vocals.
                rejected.append({"file": t.name, "reason": "ambiguous_not_verified_instrumental"})
                continue
            safe.append(t)

        if selection_out is not None:
            selection_out["rejected_tracks"] = rejected

        if safe:
            hints = mood_instrumental_hints(mood)
            ranked = _rank_by_mood(safe, hints)
            chosen = ranked[0]
            reason = f"verified_instrumental:{mood or 'default'}"

    # Shared fallback for both paths: an empty BGM dir (or every track rejected as
    # vocal/ambiguous) must not ship a silent video.
    if chosen is None:
        synth = _ensure_synthetic_ambient(path, duration_seconds)
        if synth:
            chosen = synth
            reason = "synthetic_instrumental_ambient"
        elif allow_silence:
            reason = "silence_no_safe_instrumental"
        else:
            reason = "no_bgm"

    if selection_out is not None:
        selection_out.update(
            {
                "bgm_path": str(chosen) if chosen else None,
                "reason": reason,
                "vocals_allowed": vocals_allowed,
                "mood": mood or None,
                "prefer_instrumental": prefer_instrumental,
            }
        )

    return str(chosen) if chosen else None


def _is_synthetic_ambient(path: Path, tags: dict) -> bool:
    """Lavfi-generated default_ambient is known-safe instrumental."""
    name = path.name.lower()
    if "default_ambient" in name:
        return True
    enc = str(tags.get("encoder") or "").lower()
    # Our generator stamps Lavf; no title/artist → treat as safe ambient pad.
    if "lavf" in enc and not (tags.get("title") or tags.get("artist")):
        if any(k in name for k in ("ambient", "drone", "pad", "score", "cinematic")):
            return True
    return False


def _rank_by_mood(tracks: list[Path], hints: list[str]) -> list[Path]:
    if not hints:
        return list(tracks)

    def score(p: Path) -> tuple[int, str]:
        name = p.name.lower()
        hit = sum(1 for h in hints if h in name)
        # Prefer ambient/cinematic class for documentary
        bonus = 1 if any(t in name for t in ("ambient", "cinematic", "dark", "score")) else 0
        return (-(hit + bonus), p.name)

    return sorted(tracks, key=score)


def _ensure_synthetic_ambient(path: Path, duration_seconds: float) -> Path | None:
    default_bgm = path / "default_ambient.mp3"
    if default_bgm.is_file() and default_bgm.stat().st_size > 1024:
        tags = read_audio_tags(default_bgm)
        # If someone dropped a vocal file named default_ambient, reject and regen.
        if looks_vocal_track(default_bgm.name) or track_has_vocal_metadata(tags):
            try:
                default_bgm.unlink(missing_ok=True)
            except Exception:
                return None
        else:
            return default_bgm

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", (
                f"aevalsrc=sin(130*2*PI*t)*0.03+sin(196*2*PI*t)*0.03+"
                f"sin(261*2*PI*t)*0.02:s=44100:d={int(duration_seconds) + 10}"
            ),
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            "-metadata", "title=default_ambient_instrumental",
            "-metadata", "genre=instrumental ambient",
            "-metadata", "comment=synthetic_no_vocals",
            str(default_bgm),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and default_bgm.is_file():
            return default_bgm
    except Exception:
        pass
    return None
