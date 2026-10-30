"""Stage D.1 — remote VLM adapter regression tests (offline + optional live)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled
from app.documentary_v2.schemas import PreviewFrame, VisualPreviewBundle, VisualVerificationRequest
from app.documentary_v2.verifier.capabilities import (
    GROQ_QWEN38_CAPS,
    capabilities_for_model,
    normalize_groq_model_id,
)
from app.documentary_v2.verifier.diagnostics import assert_no_secrets, build_diagnostics
from app.documentary_v2.verifier.prompt import parse_json_response
from app.documentary_v2.verifier.remote_vlm import (
    GATEWAY_IMAGE_DROPPED,
    RemoteVLMVerifier,
    build_multimodal_user_content,
    count_image_parts,
    detect_image_drop,
    frame_to_data_url,
    strip_reasoning_contamination,
)
from app.documentary_v2.verifier.temporal_batch import (
    aggregate_temporal_observations,
    plan_temporal_batches,
)
from app.documentary_v2.verifier.transport_schema import CANARY_OBJECT_SCHEMA


def _img(path: Path, color=(10, 80, 160)) -> Path:
    Image.new("RGB", (64, 64), color).save(path)
    return path


@pytest.fixture(autouse=True)
def _v2_off(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def test_v2_remains_off():
    assert documentary_engine_v2_enabled() is False


def test_provider_max_images_is_3_for_qwen():
    caps = capabilities_for_model("groq/qwen/qwen3.8-27b")
    assert caps.max_images_per_request == 3
    assert caps.model_id == "qwen/qwen3.8-27b"
    assert GROQ_QWEN38_CAPS.max_images_per_request == 3


def test_normalize_groq_model_id():
    assert normalize_groq_model_id("groq/qwen/qwen3.8-27b") == "qwen/qwen3.8-27b"
    assert normalize_groq_model_id("qwen/qwen3.8-27b") == "qwen/qwen3.8-27b"


def test_batching_over_3_frames(tmp_path: Path):
    frames = [
        PreviewFrame(timestamp_sec=float(i), path=str(_img(tmp_path / f"f{i}.jpg")))
        for i in range(6)
    ]
    batches = plan_temporal_batches(frames, max_images_per_request=3)
    assert len(batches) == 2
    assert all(len(b) <= 3 for b in batches)
    # Interleave: batch0 gets 0,2,4
    assert [f.timestamp_sec for f in batches[0]] == [0.0, 2.0, 4.0]
    assert [f.timestamp_sec for f in batches[1]] == [1.0, 3.0, 5.0]


def test_observe_batches_instead_of_illegal_send(tmp_path: Path):
    frames = [
        PreviewFrame(timestamp_sec=float(i), path=str(_img(tmp_path / f"f{i}.jpg", (i * 20, 40, 60))))
        for i in range(5)
    ]
    bundle = VisualPreviewBundle(candidate_id="c1", frames=frames, media_kind="video")
    req = VisualVerificationRequest(
        verification_id="v1",
        required_visual_concept="watch",
        required_entities=["watch"],
    )
    v = RemoteVLMVerifier(
        transport="direct_groq",
        api_key="gsk_test",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        model="qwen/qwen3.8-27b",
    )
    calls: list[int] = []

    def fake_single(request, sub_bundle, batch_frames):
        calls.append(len(batch_frames))
        assert len(batch_frames) <= 3
        return {
            "visible_entities": [],
            "visible_objects": ["water"],
            "visible_actions": [],
            "visible_setting": "outdoors",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "",
            "dominant_visual_concept": "river",
            "entity_alignment": "NONE",
            "concept_alignment": "NONE",
            "action_alignment": "NONE",
            "location_alignment": "NONE",
            "entity_specificity": "UNRELATED",
            "motion_value": "NATURAL_SUBJECT_MOTION",
            "visual_role": "UNRELATED",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": ["river"],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": True,
            "visual_supported_claims": [],
            "metadata_supported_claims": [],
            "entity_presence_ratio": 0.0,
            "concept_presence_ratio": 0.0,
            "pixels_consistent_with_archival_portrait": False,
            "preview_unusable": False,
            "confidence": 0.9,
            "explanation_short": "river",
        }

    with patch.object(v, "_observe_single_request", side_effect=fake_single):
        out = v.observe(req, bundle)
    assert len(calls) == 2
    assert all(c <= 3 for c in calls)
    assert out["metadata_visual_conflict"] is True


def test_one_image_strict_schema_parse():
    text = json.dumps(
        {
            "contains_watch": False,
            "contains_river": True,
            "contains_bakery": False,
            "summary": "river scene",
        }
    )
    data = parse_json_response(text)
    assert data["contains_river"] is True
    for k in CANARY_OBJECT_SCHEMA["required"]:
        assert k in data


def test_invalid_schema_response_fails_closed():
    with pytest.raises(json.JSONDecodeError):
        parse_json_response("not-json at all")


def test_reasoning_contamination_stripped():
    contaminated = (
        "<think>I should invent a watch</think>"
        '{"contains_watch": false, "contains_river": true, '
        '"contains_bakery": false, "summary": "river"}'
    )
    cleaned = strip_reasoning_contamination(contaminated)
    data = parse_json_response(cleaned)
    assert data["contains_watch"] is False
    assert "<think>" not in cleaned


def test_image_url_data_uri_payload(tmp_path: Path):
    p = _img(tmp_path / "a.jpg")
    url = frame_to_data_url(str(p))
    assert url.startswith("data:image/jpeg;base64,")
    frames = [PreviewFrame(timestamp_sec=0.0, path=str(p))]
    content = build_multimodal_user_content("probe", frames)
    assert count_image_parts(content) == 1
    img_part = next(p for p in content if p.get("type") == "image_url")
    assert "image_url" in img_part
    assert img_part["image_url"]["url"].startswith("data:image/")


def test_gateway_image_drop_detected():
    assert detect_image_drop(image_count=1, prompt_tokens=66) is True
    assert detect_image_drop(image_count=1, prompt_tokens=2200) is False
    assert detect_image_drop(image_count=3, prompt_tokens=100) is True


def test_direct_vs_gateway_route_distinction(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_direct_test_key")
    monkeypatch.setenv("LLM_API_URL", "http://127.0.0.1:20128/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "air_live_test")
    d = RemoteVLMVerifier(transport="direct_groq", model="groq/qwen/qwen3.8-27b")
    g = RemoteVLMVerifier(transport="gateway", model="groq/qwen/qwen3.8-27b")
    assert d.route == "direct_groq"
    assert "groq.com" in d.api_url
    assert d.model == "qwen/qwen3.8-27b"
    assert g.route == "gateway"
    assert "20128" in g.api_url
    assert g.model.startswith("groq/") or "qwen" in g.model


def test_secrets_never_logged():
    d = build_diagnostics(
        http_status=200,
        response_headers={"Authorization": "Bearer gsk_SECRETkey1234567890"},
        raw_body_excerpt='{"Authorization":"Bearer gsk_SECRETkey1234567890"}',
        model_id="qwen/qwen3.8-27b",
        image_count=1,
    )
    assert_no_secrets(d)
    assert d["response_headers"]["Authorization"] == "[REDACTED]"


def test_temporal_aggregate_not_strong_from_flash():
    batch_a = {
        "visible_entities": ["Rolex"],
        "visible_objects": ["watch"],
        "visible_actions": [],
        "visible_setting": "macro",
        "dominant_visual_concept": "luxury watch",
        "entity_alignment": "STRONG",
        "concept_alignment": "STRONG",
        "action_alignment": "NONE",
        "location_alignment": "NONE",
        "entity_specificity": "EXACT_ENTITY",
        "motion_value": "STATIC_VIDEO",
        "visual_role": "ILLUSTRATION",
        "authenticity_support": "STOCK_ILLUSTRATION",
        "genericness": "LOW",
        "contradictions": [],
        "forbidden_concept_hits": [],
        "metadata_visual_conflict": False,
        "visual_supported_claims": ["watch"],
        "metadata_supported_claims": [],
        "entity_presence_ratio": 1.0,
        "concept_presence_ratio": 1.0,
        "confidence": 0.9,
        "explanation_short": "watch frame",
    }
    batch_b = {
        "visible_entities": [],
        "visible_objects": ["river"],
        "visible_actions": ["flowing"],
        "visible_setting": "outdoors",
        "dominant_visual_concept": "river",
        "entity_alignment": "NONE",
        "concept_alignment": "NONE",
        "action_alignment": "NONE",
        "location_alignment": "NONE",
        "entity_specificity": "UNRELATED",
        "motion_value": "NATURAL_SUBJECT_MOTION",
        "visual_role": "UNRELATED",
        "authenticity_support": "STOCK_ILLUSTRATION",
        "genericness": "HIGH",
        "contradictions": ["river dominates"],
        "forbidden_concept_hits": [],
        "metadata_visual_conflict": True,
        "visual_supported_claims": [],
        "metadata_supported_claims": ["Rolex"],
        "entity_presence_ratio": 0.0,
        "concept_presence_ratio": 0.0,
        "confidence": 0.95,
        "explanation_short": "river frames",
    }
    # 1 watch frame vs 5 river frames
    out = aggregate_temporal_observations(
        [batch_a, batch_b],
        total_frame_count=6,
        batch_frame_counts=[1, 5],
    )
    assert out["entity_presence_ratio"] < 0.34
    assert out["entity_alignment"] in {"WEAK", "PARTIAL", "NONE"}
    assert out["metadata_visual_conflict"] is True
    assert any("temporal_mixed" in c or "river" in c.lower() for c in out["contradictions"])


def test_chat_detects_gateway_drop(tmp_path: Path):
    p = _img(tmp_path / "r.jpg")
    frames = [PreviewFrame(timestamp_sec=0.0, path=str(p))]
    v = RemoteVLMVerifier(
        transport="gateway",
        api_key="air_test",
        api_url="http://example.invalid/v1/chat/completions",
        model="groq/qwen/qwen3.8-27b",
    )
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {"content-type": "application/json"}
    fake_resp.text = json.dumps(
        {
            "choices": [{"message": {"content": json.dumps({
                "contains_watch": True,
                "contains_river": False,
                "contains_bakery": True,
                "summary": "hallucination without pixels",
            })}}],
            "usage": {"prompt_tokens": 66, "completion_tokens": 40},
        }
    )
    fake_resp.json.return_value = json.loads(fake_resp.text)

    # remote_vlm builds its own requests.Session() inside _chat, so patch the class.
    with patch("requests.Session") as sess_cls:
        sess_cls.return_value.post.return_value = fake_resp
        with pytest.raises(RuntimeError) as ei:
            v.chat_structured(
                text="identify river watch bakery",
                frames=frames,
                schema=CANARY_OBJECT_SCHEMA,
                schema_name="canary",
                strict=False,
            )
    assert GATEWAY_IMAGE_DROPPED in str(ei.value)


@pytest.mark.skipif(
    os.environ.get("STAGE_D1_LIVE") != "true",
    reason="Set STAGE_D1_LIVE=true for real remote canaries",
)
def test_live_remote_canaries_placeholder():
    """Live canaries run via video-output/_stage_d1_probes.py — keep pytest marker."""
    assert os.environ.get("GROQ_API_KEY") or Path(
        r"C:\Projects\sosyal-medya-otomasyon\video-output\_groq_key.txt"
    ).is_file()


def test_no_render_publish_flags_in_module():
    # Safety: D.1 modules must not import render/publish
    import app.documentary_v2.verifier.remote_vlm as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "render_video" not in src
    assert "publish" not in src.lower() or "publisher" not in src
