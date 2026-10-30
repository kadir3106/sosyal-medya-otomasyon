"""Candidate deduplication — source uniqueness, not visual information."""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.documentary_v2.providers.base import normalize_url
from app.documentary_v2.schemas import (
    AcquisitionCounts,
    DuplicateKind,
    DuplicateRelation,
    MediaCandidate,
)


def binary_hash(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def url_fingerprint(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:24]


def source_fingerprint(provider: str, source_id: str) -> str:
    return f"{provider}:{source_id}".lower()


def average_hash_bytes(data: bytes, size: int = 8) -> str:
    """Simple aHash on raw bytes resized via PIL when available; else sha of bytes."""
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(data)).convert("L").resize((size, size))
        pixels = list(img.getdata())
        avg = sum(pixels) / max(len(pixels), 1)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return f"ahash:{int(bits, 2):0{size * size // 4}x}"
    except Exception:
        return f"sha:{hashlib.sha256(data).hexdigest()[:16]}"


def hamming(a: str, b: str) -> int | None:
    if not a or not b or ":" not in a or ":" not in b:
        return None
    _, ha = a.split(":", 1)
    _, hb = b.split(":", 1)
    if len(ha) != len(hb):
        return None
    try:
        xa, xb = int(ha, 16), int(hb, 16)
    except ValueError:
        return None
    return bin(xa ^ xb).count("1")


def compare_candidates(a: MediaCandidate, b: MediaCandidate) -> DuplicateRelation:
    evidence: list[str] = []
    kind = DuplicateKind.UNIQUE.value
    confidence = 1.0

    pa, pb = a.provenance, b.provenance
    if pa.provider and pa.source_id and (
        pa.provider == pb.provider and str(pa.source_id) == str(pb.source_id)
    ):
        evidence.append("same_source_id")
        kind = DuplicateKind.EXACT_DUPLICATE.value
        confidence = 1.0
    elif normalize_url(pa.source_url) and normalize_url(pa.source_url) == normalize_url(
        pb.source_url
    ):
        evidence.append("same_url")
        kind = DuplicateKind.EXACT_DUPLICATE.value
        confidence = 0.99
    elif normalize_url(a.download_url or pa.download_url) and normalize_url(
        a.download_url or pa.download_url
    ) == normalize_url(b.download_url or pb.download_url):
        evidence.append("same_download_url")
        kind = DuplicateKind.EXACT_DUPLICATE.value
        confidence = 0.98
    elif (
        a.content_fingerprint
        and b.content_fingerprint
        and a.content_fingerprint == b.content_fingerprint
    ):
        evidence.append("same_binary_hash")
        kind = DuplicateKind.EXACT_DUPLICATE.value
        confidence = 1.0
    else:
        dist = hamming(a.perceptual_fingerprint, b.perceptual_fingerprint)
        if dist is not None and dist <= 5:
            evidence.append("perceptual_similarity")
            kind = DuplicateKind.LIKELY_DUPLICATE.value
            confidence = max(0.5, 1.0 - dist / 10.0)
        elif not evidence:
            kind = DuplicateKind.UNIQUE.value
            confidence = 1.0

    return DuplicateRelation(
        left_candidate_id=a.candidate_id,
        right_candidate_id=b.candidate_id,
        kind=kind,
        confidence=confidence,
        evidence=evidence,
    )


def dedupe_candidates(
    candidates: list[MediaCandidate],
) -> tuple[list[MediaCandidate], list[DuplicateRelation], AcquisitionCounts]:
    """Mark duplicates; keep first UNIQUE as representative. Do not merge uncertain."""
    relations: list[DuplicateRelation] = []
    kept: list[MediaCandidate] = []
    for cand in candidates:
        matched = False
        for prev in kept:
            rel = compare_candidates(cand, prev)
            if rel.kind in {
                DuplicateKind.EXACT_DUPLICATE.value,
                DuplicateKind.LIKELY_DUPLICATE.value,
            }:
                relations.append(rel)
                cand.duplicate_kind = rel.kind
                cand.duplicate_of = prev.candidate_id
                matched = True
                break
        if not matched:
            cand.duplicate_kind = DuplicateKind.UNIQUE.value
            cand.duplicate_of = ""
            kept.append(cand)

    counts = AcquisitionCounts(
        search_result_count=len(candidates),
        candidate_count=len(candidates),
        unique_candidate_count=len(kept),
        unique_source_asset_count=len(kept),
        visual_information_unit_count=0,
    )
    # Return all (with duplicate marks) for telemetry; callers may filter UNIQUE
    return candidates, relations, counts
