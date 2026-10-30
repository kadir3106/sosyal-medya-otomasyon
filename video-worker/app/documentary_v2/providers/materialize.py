"""Safe materialization: timeouts, size limits, path safety, basic integrity."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

from app.documentary_v2.providers.base import utc_now
from app.documentary_v2.providers.dedup import binary_hash
from app.documentary_v2.schemas import AssetOrigin, MediaAsset, MediaCandidate

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
DEFAULT_MAX_BYTES = 80 * 1024 * 1024  # 80MB
DEFAULT_TIMEOUT = 45


class MaterializeError(Exception):
    pass


def safe_filename(candidate_id: str, url: str = "", suffix: str = "") -> str:
    """Never trust remote filename; keep under job dir with sanitized name."""
    ext = suffix
    if not ext and url:
        path = urlparse(url).path
        guess = Path(path).suffix.lower()
        if guess in {".mp4", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = guess
    if not ext:
        ext = ".bin"
    base = _SAFE_NAME.sub("_", candidate_id)[:80] or "asset"
    return f"{base}{ext}"


def assert_inside(job_dir: Path, target: Path) -> Path:
    job_dir = job_dir.resolve()
    target = target.resolve()
    if not str(target).startswith(str(job_dir)):
        raise MaterializeError("path_escape_blocked")
    return target


def materialize_candidate(
    candidate: MediaCandidate,
    *,
    job_dir: Path | str,
    quality: str = "default",
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    session=None,
) -> MediaAsset:
    """Download selected candidate only — not all search results."""
    from app.http_client import session as default_session

    sess = session or default_session
    job = Path(job_dir)
    selected = job / "media" / "selected"
    selected.mkdir(parents=True, exist_ok=True)

    url = candidate.download_url or candidate.provenance.download_url
    if not url:
        raise MaterializeError("missing_download_url")

    name = safe_filename(candidate.candidate_id, url)
    dest = assert_inside(job, selected / name)

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        resp = sess.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        written = 0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise MaterializeError("max_size_exceeded")
                f.write(chunk)
        if written <= 0:
            raise MaterializeError("empty_download")
        tmp.replace(dest)
    except MaterializeError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise MaterializeError(f"download_failed:{exc}") from exc

    validate_media_file(dest, expected_type=candidate.provenance.media_type, content_type=ctype)

    prov = candidate.provenance
    prov.download_url = url
    prov.content_fingerprint = binary_hash(dest)
    prov.retrieved_at = prov.retrieved_at or utc_now()

    origin = AssetOrigin.STOCK.value
    if prov.archive:
        origin = AssetOrigin.ARCHIVE.value
    elif prov.synthetic:
        origin = AssetOrigin.GENERATED.value

    return MediaAsset(
        asset_id=f"asset:{prov.provider}:{prov.source_id or candidate.candidate_id}",
        provenance=prov,
        local_path=str(dest),
        origin=origin,
    )


def validate_media_file(
    path: Path,
    *,
    expected_type: str = "",
    content_type: str = "",
) -> None:
    if not path.is_file():
        raise MaterializeError("file_missing")
    if path.stat().st_size <= 0:
        raise MaterializeError("zero_size")

    # Soft content-type check
    if content_type and content_type not in {
        "application/octet-stream",
        "binary/octet-stream",
    }:
        if expected_type and "video" in expected_type and not content_type.startswith(
            ("video/", "application/")
        ):
            if not content_type.startswith("image/"):
                # allow image stills marked oddly
                pass
        if expected_type and (
            "photo" in expected_type or "still" in expected_type or "image" in expected_type
        ):
            if content_type and not (
                content_type.startswith("image/") or content_type.startswith("application/")
            ):
                raise MaterializeError(f"content_type_mismatch:{content_type}")

    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        try:
            from PIL import Image

            with Image.open(path) as im:
                im.verify()
        except Exception as exc:
            raise MaterializeError(f"invalid_image:{exc}") from exc
    elif suffix in {".mp4", ".webm", ".mov"}:
        # Prefer ffprobe when available; else magic-byte / size check
        try:
            import json
            import subprocess

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
                raise MaterializeError("ffprobe_failed")
            data = json.loads(out.stdout or "{}")
            if not (data.get("streams") or data.get("format")):
                raise MaterializeError("ffprobe_empty")
        except FileNotFoundError:
            # No ffprobe — accept non-empty file with video extension
            if path.stat().st_size < 128:
                raise MaterializeError("video_too_small")
        except MaterializeError:
            raise
        except Exception as exc:
            raise MaterializeError(f"video_validate_failed:{exc}") from exc
