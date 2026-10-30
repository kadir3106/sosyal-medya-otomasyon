"""Remote VLM adapter — Direct Groq preferred; AIRouter gateway documented as incompatible.

Stage D.1: structured multimodal via OpenAI-compatible Chat Completions.
Images as image_url data URIs. Provider max_images_per_request respected via batching.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from app.documentary_v2.schemas import PreviewFrame, VisualPreviewBundle, VisualVerificationRequest
from app.documentary_v2.verifier.base import VisualVerifierProvider
from app.documentary_v2.verifier.capabilities import (
    VLMProviderCapabilities,
    capabilities_for_model,
    normalize_groq_model_id,
)
from app.documentary_v2.verifier.diagnostics import build_diagnostics
from app.documentary_v2.verifier.prompt import (
    build_user_prompt,
    parse_json_response,
    validate_observation,
)
from app.documentary_v2.verifier.reason_codes import VLM_INVALID_RESPONSE
from app.documentary_v2.verifier.temporal_batch import (
    aggregate_temporal_observations,
    plan_temporal_batches,
)
from app.documentary_v2.verifier.transport_schema import (
    VISUAL_TRANSPORT_SCHEMA,
    response_format_json_object,
    response_format_json_schema,
    transport_to_observation,
)

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.I)
GATEWAY_IMAGE_DROPPED = "GATEWAY_IMAGE_DROPPED"
TOO_MANY_IMAGES = "TOO_MANY_IMAGES"


def _chat_url(base: str) -> str:
    b = (base or "").rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    return f"{b}/chat/completions"


def _mime_for(path: str) -> str:
    p = path.lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def frame_to_data_url(path: str, *, max_side: int = 768, jpeg_quality: int = 75) -> str:
    """Encode local image as data URI. Downscale to keep Groq ITPM budgets sane."""
    p = Path(path)
    try:
        from PIL import Image
        import io

        with Image.open(p) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, float(max_side) / float(max(w, h)))
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        raw = p.read_bytes()
        mime = _mime_for(path)
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"


def build_multimodal_user_content(
    text: str,
    frames: list[PreviewFrame],
    *,
    label_frames: bool = True,
) -> list[dict[str, Any]]:
    """OpenAI-compatible multimodal content parts (never flatten images into text)."""
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for i, fr in enumerate(frames):
        if not fr.path or not Path(fr.path).is_file():
            continue
        if label_frames:
            content.append(
                {
                    "type": "text",
                    "text": f"[frame_index={i} timestamp_sec={fr.timestamp_sec} source={fr.source}]",
                }
            )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": frame_to_data_url(fr.path)},
            }
        )
    return content


def count_image_parts(content: list[dict]) -> int:
    return sum(1 for p in content if isinstance(p, dict) and p.get("type") == "image_url")


def strip_reasoning_contamination(text: str) -> str:
    raw = _THINK_RE.sub("", text or "").strip()
    return raw


def detect_image_drop(
    *,
    image_count: int,
    prompt_tokens: int | None,
    tokens_per_image_approx: int = 2048,
) -> bool:
    """Heuristic: Groq counts ~2048 tokens/image. Text-only prompts are ~50–200 tokens."""
    if image_count <= 0 or prompt_tokens is None:
        return False
    # Require at least ~half an image-token budget; below that images were stripped.
    min_expected = max(800, int(tokens_per_image_approx * image_count * 0.4))
    return int(prompt_tokens) < min_expected


class RemoteVLMVerifier(VisualVerifierProvider):
    """Remote multimodal VisualVerifier.

    Routes:
      - direct_groq: https://api.groq.com/openai/v1 (preferred for vision)
      - gateway: LLM_API_URL / AIRouter (text OK; currently STRIPS image_url → fail-closed)
      - auto: GROQ_API_KEY → direct_groq else gateway
    """

    name = "remote_vlm"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 1,
        transport: str | None = None,
        capabilities: VLMProviderCapabilities | None = None,
        use_system_prompt: bool = False,
    ) -> None:
        from app.config import config

        self.transport = (
            transport
            or os.environ.get("VISUAL_VERIFIER_TRANSPORT")
            or getattr(config, "VISUAL_VERIFIER_TRANSPORT", "auto")
            or "auto"
        ).lower()
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_system_prompt = use_system_prompt
        self.last_diagnostics: dict[str, Any] = {}
        self._batch_telemetry: list[dict[str, Any]] = []

        configured_model = (
            model
            or getattr(config, "VISUAL_VERIFIER_MODEL", "")
            or getattr(config, "OPENROUTER_MODEL", "")
            or "qwen/qwen3.8-27b"
        )
        self.configured_model = configured_model
        self.capabilities = capabilities or capabilities_for_model(configured_model)

        groq_key = os.environ.get("GROQ_API_KEY") or getattr(config, "GROQ_API_KEY", "") or ""
        gateway_key = (
            getattr(config, "OPENROUTER_API_KEY", "")
            or os.environ.get("OPENROUTER_API_KEY", "")
        )
        gateway_url = getattr(config, "LLM_API_URL", "") or os.environ.get("LLM_API_URL", "")

        resolved = self._resolve_route(
            transport=self.transport,
            groq_key=groq_key,
            gateway_key=gateway_key,
            gateway_url=gateway_url,
            explicit_url=api_url,
            explicit_key=api_key,
        )
        self.route = resolved["route"]
        self.api_url = resolved["api_url"]
        self.api_key = resolved["api_key"]
        self.model = resolved["model"]
        self.name = f"remote_vlm:{self.route}"

    def _resolve_route(
        self,
        *,
        transport: str,
        groq_key: str,
        gateway_key: str,
        gateway_url: str,
        explicit_url: str | None,
        explicit_key: str | None,
    ) -> dict[str, str]:
        groq_url = os.environ.get(
            "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
        )
        model_direct = normalize_groq_model_id(self.configured_model)
        model_gateway = self.configured_model

        if transport == "direct_groq":
            key = explicit_key if explicit_key is not None else groq_key
            return {
                "route": "direct_groq",
                "api_url": _chat_url(explicit_url or groq_url),
                "api_key": key or "",
                "model": model_direct,
            }
        if transport == "gateway":
            key = explicit_key if explicit_key is not None else gateway_key
            return {
                "route": "gateway",
                "api_url": _chat_url(explicit_url or gateway_url),
                "api_key": key or "",
                "model": model_gateway,
            }
        # auto
        if groq_key or (explicit_key and not gateway_url):
            key = explicit_key if explicit_key is not None else groq_key
            if key:
                return {
                    "route": "direct_groq",
                    "api_url": _chat_url(groq_url),
                    "api_key": key,
                    "model": model_direct,
                }
        return {
            "route": "gateway",
            "api_url": _chat_url(gateway_url or "https://openrouter.ai/api/v1/chat/completions"),
            "api_key": (explicit_key if explicit_key is not None else gateway_key) or "",
            "model": model_gateway,
        }

    @property
    def available(self) -> bool:
        return bool(self.api_url and self.api_key)

    def observe(
        self,
        request: VisualVerificationRequest,
        bundle: VisualPreviewBundle,
    ) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("VLM_UNAVAILABLE: missing api_url/api_key")

        frames = [f for f in bundle.frames if f.path and Path(f.path).is_file()]
        if not frames:
            raise RuntimeError(f"{VLM_INVALID_RESPONSE}:no_frame_files")

        max_img = int(self.capabilities.max_images_per_request)
        batches = plan_temporal_batches(frames, max_images_per_request=max_img)
        self._batch_telemetry = []
        if len(frames) > max_img:
            self._batch_telemetry.append(
                {
                    "event": "temporal_batching",
                    "frame_count": len(frames),
                    "max_images_per_request": max_img,
                    "batch_count": len(batches),
                    "batch_sizes": [len(b) for b in batches],
                }
            )
            log.info(
                "remote_vlm temporal_batching frames=%s max=%s batches=%s",
                len(frames),
                max_img,
                [len(b) for b in batches],
            )

        batch_obs: list[dict[str, Any]] = []
        batch_counts: list[int] = []
        for bi, batch_frames in enumerate(batches):
            if len(batch_frames) > max_img:
                # Should never happen if planner works — fail closed, never ACCEPT
                raise RuntimeError(
                    f"{VLM_INVALID_RESPONSE}:{TOO_MANY_IMAGES}:batch={bi}:n={len(batch_frames)}:max={max_img}"
                )
            if bi > 0:
                # Pace batches to stay under provider ITPM (Groq free tier ~7k).
                time.sleep(float(os.environ.get("VLM_BATCH_PAUSE_SEC", "20")))
            sub_bundle = VisualPreviewBundle(
                candidate_id=bundle.candidate_id,
                media_kind=bundle.media_kind,
                duration_sec=bundle.duration_sec,
                width=bundle.width,
                height=bundle.height,
                frames=batch_frames,
                preview_clip_path=bundle.preview_clip_path,
                content_fingerprint=bundle.content_fingerprint,
                technical={
                    **(bundle.technical or {}),
                    "temporal_batch_index": bi,
                    "temporal_batch_count": len(batches),
                },
            )
            obs = self._observe_single_request(request, sub_bundle, batch_frames)
            batch_obs.append(obs)
            batch_counts.append(len(batch_frames))

        if len(batch_obs) == 1:
            out = batch_obs[0]
        else:
            out = aggregate_temporal_observations(
                batch_obs,
                total_frame_count=len(frames),
                batch_frame_counts=batch_counts,
            )
        if self._batch_telemetry:
            out["_batch_telemetry"] = list(self._batch_telemetry)
        return out

    def _observe_single_request(
        self,
        request: VisualVerificationRequest,
        bundle: VisualPreviewBundle,
        frames: list[PreviewFrame],
    ) -> dict[str, Any]:
        user_text = build_user_prompt(request, bundle, compact=True)
        # Prefer instructions in user message (canary / Direct Groq hygiene).
        user_text = (
            "Judge ONLY visible pixels in attached frames. "
            "Return schema-valid JSON only. No markdown. No chain-of-thought.\n"
            + user_text
        )
        content = build_multimodal_user_content(user_text, frames)
        image_count = count_image_parts(content)
        if image_count == 0:
            raise RuntimeError(f"{VLM_INVALID_RESPONSE}:no_image_parts")
        if image_count > self.capabilities.max_images_per_request:
            raise RuntimeError(
                f"{VLM_INVALID_RESPONSE}:{TOO_MANY_IMAGES}:{image_count}>{self.capabilities.max_images_per_request}"
            )

        last_err = ""
        for attempt in range(self.max_retries + 1):
            try:
                raw_text, meta = self._chat(
                    content,
                    schema=VISUAL_TRANSPORT_SCHEMA,
                    schema_name="visual_verification",
                    repair=(attempt > 0),
                )
                cleaned = strip_reasoning_contamination(raw_text)
                data = parse_json_response(cleaned)
                data = transport_to_observation(data)
                ok, why = validate_observation(data)
                if not ok:
                    last_err = why
                    if attempt < self.max_retries:
                        content = [
                            {
                                "type": "text",
                                "text": (
                                    f"Previous response invalid ({why}). "
                                    "Return ONLY schema-valid JSON.\n" + user_text
                                ),
                            }
                        ] + [p for p in content if p.get("type") == "image_url" or (
                            p.get("type") == "text" and str(p.get("text", "")).startswith("[frame_index=")
                        )]
                        continue
                    raise RuntimeError(f"{VLM_INVALID_RESPONSE}:{why}")
                data["_meta"] = {
                    "route": self.route,
                    "model": self.model,
                    "image_count": image_count,
                    "prompt_tokens": meta.get("prompt_tokens"),
                    "latency_ms": meta.get("latency_ms"),
                }
                return data
            except RuntimeError:
                raise
            except Exception as exc:
                last_err = str(exc)[:200]
                if attempt >= self.max_retries:
                    raise RuntimeError(f"{VLM_INVALID_RESPONSE}:{last_err}") from exc
        raise RuntimeError(f"{VLM_INVALID_RESPONSE}:{last_err}")

    def chat_structured(
        self,
        *,
        text: str,
        frames: list[PreviewFrame],
        schema: dict[str, Any],
        schema_name: str = "result",
        strict: bool | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Low-level structured multimodal call (probes / diagnostics)."""
        if not self.available:
            raise RuntimeError("VLM_UNAVAILABLE: missing api_url/api_key")
        content = build_multimodal_user_content(text, frames)
        image_count = count_image_parts(content)
        if image_count > self.capabilities.max_images_per_request:
            raise RuntimeError(
                f"{VLM_INVALID_RESPONSE}:{TOO_MANY_IMAGES}:{image_count}"
            )
        raw_text, meta = self._chat(
            content,
            schema=schema,
            schema_name=schema_name,
            strict=strict,
        )
        cleaned = strip_reasoning_contamination(raw_text)
        data = parse_json_response(cleaned)
        return data, {**meta, "raw_text_excerpt": cleaned[:500]}

    def _chat(
        self,
        content: list[dict],
        *,
        schema: dict[str, Any] | None = None,
        schema_name: str = "result",
        repair: bool = False,
        strict: bool | None = None,
    ) -> tuple[str, dict[str, Any]]:
        # Dedicated session: app.http_client retries 429 with Retry-After and can
        # hang for many minutes on Groq free-tier. VisualVerifier must fail fast.
        import requests

        sess = requests.Session()
        timeout = (10.0, float(self.timeout))

        image_count = count_image_parts(content)
        want_strict = (
            self.capabilities.supports_strict_schema
            if strict is None
            else strict
        )
        # Groq qwen: try json_schema (strict preferred by caller; model may only support false)
        response_format = None
        response_format_mode = ""
        if schema is not None and self.capabilities.supports_json_schema:
            # Prefer strict=True first when requested; fall back inside retry below
            use_strict = True if strict is True else bool(want_strict)
            if strict is None and not self.capabilities.supports_strict_schema:
                use_strict = False
            response_format = response_format_json_schema(
                schema, name=schema_name, strict=use_strict
            )
            response_format_mode = f"json_schema:strict={use_strict}"
        elif self.capabilities.supports_json_object:
            response_format = response_format_json_object()
            response_format_mode = "json_object"

        reasoning_config: dict[str, Any] = {}
        if self.capabilities.reasoning_effort:
            reasoning_config["reasoning_effort"] = self.capabilities.reasoning_effort
        # Do NOT set reasoning_format alongside conflicting include_reasoning.

        messages: list[dict[str, Any]] = []
        if self.use_system_prompt:
            from app.documentary_v2.verifier.prompt import SYSTEM_PROMPT

            messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": content})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1 if not repair else 0.0,
            "max_completion_tokens": 2048,
        }
        if response_format is not None:
            body["response_format"] = response_format
        body.update(reasoning_config)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        t0 = time.perf_counter()
        resp = sess.post(self.api_url, headers=headers, json=body, timeout=timeout)
        latency_ms = (time.perf_counter() - t0) * 1000

        # If strict schema rejected, one fallback to strict:false then json_object
        if resp.status_code >= 400 and schema is not None and "json_schema" in response_format_mode:
            err_txt = sanitize_excerpt(resp.text)
            if "strict" in err_txt.lower() or "json_schema" in err_txt.lower() or resp.status_code == 400:
                body["response_format"] = response_format_json_schema(
                    schema, name=schema_name, strict=False
                )
                response_format_mode = "json_schema:strict=false"
                t0 = time.perf_counter()
                resp = sess.post(
                    self.api_url, headers=headers, json=body, timeout=timeout
                )
                latency_ms = (time.perf_counter() - t0) * 1000

        if resp.status_code >= 400 and schema is not None and self.capabilities.supports_json_object:
            if resp.status_code == 400:
                body["response_format"] = response_format_json_object()
                response_format_mode = "json_object_fallback"
                t0 = time.perf_counter()
                resp = sess.post(
                    self.api_url, headers=headers, json=body, timeout=timeout
                )
                latency_ms = (time.perf_counter() - t0) * 1000

        usage = {}
        prompt_tokens = None
        completion_tokens = None
        raw_excerpt = sanitize_excerpt(resp.text)
        try:
            data = resp.json()
            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
        except Exception:
            data = {}

        self.last_diagnostics = build_diagnostics(
            http_status=resp.status_code,
            response_headers={
                k: v
                for k, v in resp.headers.items()
                if k.lower() in {
                    "content-type",
                    "x-request-id",
                    "x-groq-region",
                    "x-airouter-provider",
                    "x-airouter-account",
                    "x-airouter-model",
                }
            },
            response_format_mode=response_format_mode,
            model_id=self.model,
            image_count=image_count,
            image_content_mode="data_url",
            reasoning_config=reasoning_config,
            raw_body_excerpt=raw_excerpt,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            route=self.route,
        )

        if resp.status_code == 429:
            raise RuntimeError("RATE_LIMITED")
        if resp.status_code == 413:
            # Groq ITPM / request-too-large — fail closed as unavailable for retry layers
            raise RuntimeError(f"RATE_LIMITED:http_413:{raw_excerpt[:180]}")
        if resp.status_code >= 400:
            self.last_diagnostics["parser_error"] = f"http_{resp.status_code}"
            raise RuntimeError(
                f"{VLM_INVALID_RESPONSE}:http_{resp.status_code}:{raw_excerpt[:180]}"
            )

        if detect_image_drop(
            image_count=image_count,
            prompt_tokens=prompt_tokens,
            tokens_per_image_approx=self.capabilities.tokens_per_image_approx,
        ):
            self.last_diagnostics["validation_error"] = GATEWAY_IMAGE_DROPPED
            raise RuntimeError(
                f"{VLM_INVALID_RESPONSE}:{GATEWAY_IMAGE_DROPPED}:"
                f"prompt_tokens={prompt_tokens}:images={image_count}:route={self.route}"
            )

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{VLM_INVALID_RESPONSE}:empty_choices")
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
        if not str(text).strip():
            # Some models put JSON in reasoning/refusal — fail closed
            raise RuntimeError(f"{VLM_INVALID_RESPONSE}:empty_response")

        meta = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "response_format_mode": response_format_mode,
            "route": self.route,
            "image_count": image_count,
        }
        return str(text), meta


def sanitize_excerpt(text: str, limit: int = 400) -> str:
    from app.documentary_v2.verifier.diagnostics import sanitize_body_excerpt

    return sanitize_body_excerpt(text, limit=limit)
