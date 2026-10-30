"""Phase 3 / 3.2 — deterministic Narration / Pacing / Music profiles (no extra LLM)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


_EMPHASIS_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "that", "this", "it", "its",
    "as", "by", "from", "at", "into", "than", "then", "but", "not", "no",
}

_MONEY_RE = re.compile(r"\$[\d,.]+|\b\d+(?:\.\d+)?\s*(?:billion|million|trillion)\b", re.I)
_PROPER_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_DARK_CUES = ("secret", "trust", "foundation", "empire", "untouchable", "ownership", "tax")

_VOCAL_NAME_HINTS = (
    "vocal", "vocals", "lyrics", "sing", "singer", "singing", "song",
    "rap", "choir", "verse", "chorus", "jpop", "j-pop", "kpop", "k-pop",
    "anime", "opening", "ending theme",
)
_VOCAL_TAG_HINTS = (
    "vocal", "vocals", "lyrics", "singing", "singer", "song", "pop",
    "j-pop", "jpop", "k-pop", "rap", "choir", "chorus",
)

_MOOD_HINTS: dict[str, tuple[str, ...]] = {
    "dark_luxury": ("dark", "luxury", "cinematic", "noir", "underscore", "score"),
    "financial_documentary": ("cinematic", "dark", "tension", "score", "ambient"),
    "mystery": ("mystery", "dark", "ambient", "drone", "tension"),
    "corporate": ("corporate", "minimal", "ambient", "underscore"),
    "technology": ("tech", "pulse", "ambient", "electronic", "score"),
    "inspirational": ("inspirational", "uplift", "cinematic", "ambient"),
    "historical": ("historical", "orchestral", "cinematic", "score", "ambient"),
    "cinematic_ambient": ("ambient", "cinematic", "pad", "drone", "score"),
}


@dataclass
class NarrationProfile:
    style: str = "premium_documentary"
    energy: float = 0.7
    pace: str = "controlled_fast"
    dramatic_level: float = 0.6
    pause_strength: float = 0.45
    emphasis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def elevenlabs_voice_settings(self) -> dict:
        """Map profile → ElevenLabs voice_settings (supported keys only)."""
        stability = max(0.35, min(0.75, 0.62 - 0.15 * self.dramatic_level))
        style = max(0.15, min(0.55, 0.2 + 0.35 * self.dramatic_level))
        similarity = max(0.65, min(0.9, 0.78 + 0.05 * self.energy))
        return {
            "stability": round(stability, 3),
            "similarity_boost": round(similarity, 3),
            "style": round(style, 3),
            "use_speaker_boost": True,
        }


@dataclass
class PacingProfile:
    hook: str = "fast_visual"
    setup: str = "controlled"
    entity_reveal: str = "brief_hold"
    claim: str = "visual_punch"
    payoff: str = "confident_slower"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MusicProfile:
    mood: str = "dark_luxury"
    intensity: float = 0.55
    vocals_allowed: bool = False
    bgm_volume: float = 0.10
    duck_threshold: float = 0.025
    duck_ratio: float = 6.0
    energy: str = "controlled"

    def to_dict(self) -> dict:
        return asdict(self)


def build_narration_profile(
    *,
    topic: str = "",
    script: str = "",
    hook: str = "",
    concrete_nouns: list | None = None,
) -> NarrationProfile:
    text = f"{topic}\n{hook}\n{script}"
    emphasis: list[str] = []
    for m in _MONEY_RE.findall(text):
        tok = str(m).strip()
        if tok and tok not in emphasis:
            emphasis.append(tok)
    for m in _PROPER_RE.findall(text):
        if m.lower() in _EMPHASIS_STOP or len(m) < 3:
            continue
        if m not in emphasis:
            emphasis.append(m)
        if len(emphasis) >= 12:
            break
    for n in concrete_nouns or []:
        s = str(n).strip()
        if s and s not in emphasis and len(emphasis) < 14:
            emphasis.append(s)

    low = text.lower()
    dark = sum(1 for c in _DARK_CUES if c in low)
    dramatic = min(0.85, 0.45 + 0.08 * dark + (0.1 if _MONEY_RE.search(text) else 0))
    words = len(script.split()) if script else 40
    pace = "controlled_fast" if words < 90 else "measured"
    energy = 0.78 if words < 70 else 0.65
    return NarrationProfile(
        style="premium_documentary",
        energy=energy,
        pace=pace,
        dramatic_level=round(dramatic, 2),
        pause_strength=0.5 if dramatic > 0.65 else 0.4,
        emphasis=emphasis[:14],
    )


def build_pacing_profile(*, script: str = "", beat_roles: list[str] | None = None) -> PacingProfile:
    roles = [str(r or "").lower() for r in (beat_roles or [])]
    notes = []
    if any("hook" in r for r in roles):
        notes.append("hook_beats_present")
    if any("entity" in r or "reveal" in r for r in roles):
        notes.append("entity_reveal_beats")
    if any(c.isdigit() for c in script) or "$" in script:
        notes.append("numeric_claim")
    return PacingProfile(notes=notes)


def build_music_profile(*, topic: str = "", script: str = "") -> MusicProfile:
    low = f"{topic} {script}".lower()
    mood = "cinematic_ambient"
    if any(
        c in low
        for c in ("tax", "trust", "foundation", "shareholder", "billion", "finance", "bank")
    ):
        mood = "financial_documentary"
    elif any(c in low for c in _DARK_CUES):
        mood = "dark_luxury"
    elif any(c in low for c in ("mystery", "secret", "hidden")):
        mood = "mystery"
    elif any(c in low for c in ("tech", "ai", "software", "digital")):
        mood = "technology"
    elif any(c in low for c in ("history", "archive", "century", "founded")):
        mood = "historical"
    elif any(c in low for c in ("inspire", "success", "motivat")):
        mood = "inspirational"
    elif any(c in low for c in ("corporate", "board", "company")):
        mood = "corporate"

    darkish = mood in {"dark_luxury", "financial_documentary", "mystery"}
    return MusicProfile(
        mood=mood,
        intensity=0.55 if darkish else 0.45,
        vocals_allowed=False,
        bgm_volume=0.08 if darkish else 0.10,
        duck_threshold=0.02,
        duck_ratio=7.0 if darkish else 5.5,
        energy="controlled",
    )


def looks_vocal_track(path_or_name: str) -> bool:
    name = str(path_or_name).lower().replace("_", " ").replace("-", " ")
    return any(h in name for h in _VOCAL_NAME_HINTS)


def looks_instrumental_track(path_or_name: str) -> bool:
    name = str(path_or_name).lower()
    if looks_vocal_track(name):
        return False
    tips = (
        "ambient", "cinematic", "instrumental", "score", "underscore",
        "lofi", "drone", "pad", "tension", "noir", "orchestra", "default_ambient",
    )
    return any(t in name for t in tips)


def read_audio_tags(path: Path | str) -> dict:
    """Best-effort ffprobe tags — empty dict if unavailable."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(p),
            ],
            text=True,
            timeout=8,
            stderr=subprocess.DEVNULL,
        )
        import json

        tags = (json.loads(out).get("format") or {}).get("tags") or {}
        return {str(k).lower(): str(v) for k, v in tags.items()}
    except Exception:
        return {}


def track_has_vocal_metadata(tags: dict | None) -> bool:
    if not tags:
        return False
    blob = " ".join(str(v) for v in tags.values()).lower()
    return any(h in blob for h in _VOCAL_TAG_HINTS)


def mood_instrumental_hints(mood: str) -> list[str]:
    return list(
        _MOOD_HINTS.get((mood or "").strip().lower(), _MOOD_HINTS["cinematic_ambient"])
    )
