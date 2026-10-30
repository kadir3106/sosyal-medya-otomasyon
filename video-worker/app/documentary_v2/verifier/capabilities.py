"""Provider capability metadata for VisualVerifier remote adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class VLMProviderCapabilities:
    """Per-provider limits — do not hardcode globally in VisualVerifier."""

    provider_id: str
    model_id: str
    supports_images: bool = True
    supports_video_native: bool = False
    supports_json_object: bool = True
    supports_json_schema: bool = True
    # Groq qwen/qwen3.8-27b: structured outputs best-effort (strict:false);
    # strict:true is not guaranteed on this model.
    supports_strict_schema: bool = False
    max_images_per_request: int = 3
    max_image_bytes: int | None = 20 * 1024 * 1024
    tokens_per_image_approx: int = 2048
    reasoning_effort: str = "none"
    reasoning_format: str | None = None  # omit by default; mutually exclusive w/ include_reasoning
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)


# Official Groq limits for qwen/qwen3.8-27b (vision + structured outputs).
GROQ_QWEN38_CAPS = VLMProviderCapabilities(
    provider_id="groq",
    model_id="qwen/qwen3.8-27b",
    supports_images=True,
    supports_video_native=False,
    supports_json_object=True,
    supports_json_schema=True,
    supports_strict_schema=False,
    max_images_per_request=3,
    max_image_bytes=20 * 1024 * 1024,
    tokens_per_image_approx=2048,
    reasoning_effort="none",
    reasoning_format=None,
    notes=(
        "MAX_INPUT_IMAGES=3",
        "use reasoning_effort=none for structured vision JSON",
        "json_schema preferred; strict true not guaranteed — try then fall back",
    ),
)


def capabilities_for_model(model_id: str) -> VLMProviderCapabilities:
    mid = (model_id or "").strip()
    # AIRouter prefixes: groq/qwen/qwen3.8-27b
    bare = mid.split("/", 1)[-1] if mid.startswith("groq/") else mid
    if bare == "qwen/qwen3.8-27b" or mid.endswith("qwen/qwen3.8-27b"):
        return GROQ_QWEN38_CAPS
    # Conservative default for unknown OpenAI-compatible vision endpoints
    return VLMProviderCapabilities(
        provider_id="openai_compatible",
        model_id=mid or "unknown",
        max_images_per_request=3,
        supports_strict_schema=False,
        notes=("unknown_model_conservative_cap=3",),
    )


def normalize_groq_model_id(model_id: str) -> str:
    """Strip AIRouter provider prefix for Direct Groq Chat Completions."""
    mid = (model_id or "").strip()
    if mid.startswith("groq/"):
        return mid[len("groq/") :]
    return mid or "qwen/qwen3.8-27b"
