"""Sanitized VLM diagnostics — never log secrets."""
from __future__ import annotations

import re
from typing import Any

_SECRET_KEYS = re.compile(
    r"(authorization|api[_-]?key|token|secret|password|credential)",
    re.I,
)
_BEARER = re.compile(r"Bearer\s+\S+", re.I)
_DATA_URI = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{32,}")


def sanitize_headers(headers: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if _SECRET_KEYS.search(str(k)):
            out[str(k)] = "[REDACTED]"
        else:
            out[str(k)] = _BEARER.sub("Bearer [REDACTED]", str(v)[:200])
    return out


def sanitize_body_excerpt(text: str, *, limit: int = 1200) -> str:
    raw = text or ""
    raw = _BEARER.sub("Bearer [REDACTED]", raw)
    raw = _DATA_URI.sub("data:image/…;base64,[REDACTED]", raw)
    if len(raw) > limit:
        return raw[:limit] + "…[truncated]"
    return raw


def build_diagnostics(
    *,
    http_status: int | None = None,
    response_headers: dict | None = None,
    response_format_mode: str = "",
    model_id: str = "",
    image_count: int = 0,
    image_content_mode: str = "",
    reasoning_config: dict | None = None,
    raw_body_excerpt: str = "",
    parser_error: str = "",
    validation_error: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    route: str = "",
    extra: dict | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "http_status": http_status,
        "response_headers": sanitize_headers(response_headers),
        "response_format_mode": response_format_mode,
        "model_id": model_id,
        "image_count": image_count,
        "image_content_mode": image_content_mode,
        "reasoning_config": dict(reasoning_config or {}),
        "raw_body_excerpt": sanitize_body_excerpt(raw_body_excerpt),
        "parser_error": (parser_error or "")[:400],
        "validation_error": (validation_error or "")[:400],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "route": route,
    }
    if extra:
        # Never allow secrets via extra
        safe = {k: v for k, v in extra.items() if not _SECRET_KEYS.search(str(k))}
        d["extra"] = safe
    return d


def assert_no_secrets(payload: Any) -> None:
    """Test helper — raise if common secret patterns appear."""
    text = str(payload)
    if "Bearer gsk_" in text or "Bearer sk-" in text:
        raise AssertionError("secret leaked in diagnostics")
    if "Authorization: Bearer " in text and "[REDACTED]" not in text:
        if re.search(r"Bearer\s+[A-Za-z0-9_\-]{20,}", text):
            raise AssertionError("authorization token leaked")
