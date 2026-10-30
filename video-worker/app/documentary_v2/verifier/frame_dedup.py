"""Frame perceptual dedup for VLM submission (not MediaCandidate dedup)."""
from __future__ import annotations

from pathlib import Path

from app.documentary_v2.providers.dedup import average_hash_bytes, hamming
from app.documentary_v2.schemas import PreviewFrame


def hash_frame_file(path: Path | str) -> str:
    data = Path(path).read_bytes()
    return average_hash_bytes(data)


def dedupe_frames(
    frames: list[PreviewFrame],
    *,
    max_hamming: int = 4,
) -> list[PreviewFrame]:
    """Drop near-identical frames before VLM submission."""
    kept: list[PreviewFrame] = []
    for fr in frames:
        ph = fr.perceptual_hash
        if fr.path and not ph:
            try:
                ph = hash_frame_file(fr.path)
                fr.perceptual_hash = ph
            except Exception:
                ph = ""
        if not ph:
            kept.append(fr)
            continue
        dup = False
        for prev in kept:
            dist = hamming(ph, prev.perceptual_hash)
            if dist is not None and dist <= max_hamming:
                dup = True
                break
        if not dup:
            kept.append(fr)
    return kept
