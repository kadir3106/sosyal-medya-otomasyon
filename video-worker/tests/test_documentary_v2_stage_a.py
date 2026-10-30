"""Documentary Engine V2 — Stage A: schemas, flag, pipeline_mode, telemetry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.documentary_v2.adapters import (
    build_production_manifest_from_legacy,
    model_call_from_airouter,
)
from app.documentary_v2.pipeline_mode import (
    V2_EXECUTION_ACTIVE,
    documentary_engine_v2_enabled,
    pipeline_mode_diagnostics,
    resolve_pipeline_mode,
    warn_if_legacy_stock,
)
from app.documentary_v2.schemas import (
    SCHEMA_VERSION,
    AssetProvenance,
    BeatTelemetry,
    GateResult,
    LicenseState,
    MediaAsset,
    ModelCallTelemetry,
    PipelineMode,
    ProductionManifest,
    QualityTelemetry,
    ShotTelemetry,
    VisualInformationUnit,
)
from app.documentary_v2.telemetry import write_production_manifest


@pytest.fixture(autouse=True)
def _clear_v2_env(monkeypatch):
    monkeypatch.delenv("DOCUMENTARY_ENGINE_V2", raising=False)
    monkeypatch.delenv("DIRECTOR_ENABLED", raising=False)
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.setenv("DIRECTOR_ENABLED", "false")
    yield


# ── Flag / pipeline_mode ───────────────────────────────────────────────


def test_v2_flag_off_by_default():
    assert documentary_engine_v2_enabled() is False
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK


def test_v2_flag_true_still_legacy_in_stage_a(monkeypatch):
    """Stage A: V2_EXECUTION_ACTIVE=False → no DOCUMENTARY_V2 mode yet."""
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "true")
    assert documentary_engine_v2_enabled() is True
    assert V2_EXECUTION_ACTIVE is False
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK


def test_director_on_is_legacy_director(monkeypatch):
    monkeypatch.setenv("DIRECTOR_ENABLED", "true")
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_DIRECTOR


def test_pipeline_mode_explicit_values():
    assert resolve_pipeline_mode(documentary_v2=False, director=False) == PipelineMode.LEGACY_STOCK
    assert resolve_pipeline_mode(documentary_v2=False, director=True) == PipelineMode.LEGACY_DIRECTOR


def test_legacy_stock_warning_logged(caplog, capsys):
    with caplog.at_level("WARNING"):
        warn_if_legacy_stock(mode=PipelineMode.LEGACY_STOCK)
    assert any("LEGACY_STOCK" in r.message for r in caplog.records)
    captured = capsys.readouterr()
    assert "LEGACY_STOCK" in captured.out
    assert "VisualVerifier" in captured.out


def test_diagnostics_include_mode_and_versions():
    d = pipeline_mode_diagnostics()
    assert d["pipeline_mode"] == "LEGACY_STOCK"
    assert d["documentary_engine_v2"] is False
    assert d["schema_version"] == "1"
    assert d["pipeline_version"] == "legacy"


def test_config_documentary_flag_property(monkeypatch):
    from app.config import config

    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    assert config.DOCUMENTARY_ENGINE_V2 is False
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "true")
    assert config.DOCUMENTARY_ENGINE_V2 is True


# ── Schemas / provenance ───────────────────────────────────────────────


def test_unknown_license_default_and_empty():
    p = AssetProvenance.from_dict({"provider": "pexels", "license": ""})
    assert p.license == LicenseState.UNKNOWN.value
    p2 = AssetProvenance()
    assert p2.license == LicenseState.UNKNOWN.value


def test_synthetic_flag_persists():
    p = AssetProvenance.from_dict(
        {"provider": "ai_image", "synthetic": True, "stock": False, "license": "UNKNOWN"}
    )
    assert p.synthetic is True
    assert p.license == "UNKNOWN"
    asset = MediaAsset(asset_id="asset:ai:1", provenance=p, origin="generated")
    d = asset.to_dict()
    assert d["provenance"]["synthetic"] is True
    assert d["provenance"]["license"] == "UNKNOWN"


def test_canonical_schemas_validate_roundtrip():
    job_id = "test-job-001"
    video_id = job_id
    beat = BeatTelemetry(
        beat_id=f"beat:{job_id}:0",
        job_id=job_id,
        video_id=video_id,
        start_time=0.0,
        end_time=3.5,
        narrative_role="HOOK",
        semantic_domain="luxury_watch",
        claim_ids=["claim:1"],
    )
    shot = ShotTelemetry(
        shot_id=f"shot:{job_id}:0",
        beat_id=beat.beat_id,
        job_id=job_id,
        video_id=video_id,
        asset_id="asset:pexels:99",
        visual_information_id=f"viu:{job_id}:0",
        provider="pexels",
        media_type="stock_video",
        origin="stock",
        stock=True,
        license=LicenseState.STOCK_LICENSED.value,
        start_time=0.0,
        end_time=3.5,
        verification_status="NOT_RUN",
    )
    viu = VisualInformationUnit(
        visual_information_id=f"viu:{job_id}:0",
        asset_id="asset:pexels:99",
        entity="Rolex Daytona",
        evidence_role="product_evidence",
        beat_id=beat.beat_id,
    )
    qt = QualityTelemetry(
        gate="StoryConsistencyGate",
        result=GateResult.PASS.value,
        reason_codes=["domain_lock_ok"],
        beat_ids=[beat.beat_id],
        job_id=job_id,
        video_id=video_id,
    )
    mc = ModelCallTelemetry(
        call_id="mc:1",
        job_id=job_id,
        video_id=video_id,
        stage="script",
        provider="airouter",
        model="gemini-flash",
        latency_ms=120.0,
        input_tokens=100,
        output_tokens=50,
        estimated_cost=0.001,
        fallback_depth=0,
        status="ok",
    )
    manifest = ProductionManifest(
        job_id=job_id,
        video_id=video_id,
        topic="Rolex Daytona",
        pipeline_mode=PipelineMode.LEGACY_STOCK.value,
        documentary_engine_v2=False,
        schema_version=SCHEMA_VERSION,
        beat_telemetry=[beat],
        shot_telemetry=[shot],
        visual_information_units=[viu],
        quality=[qt],
        model_calls=[mc],
        assets=[
            MediaAsset(
                asset_id="asset:pexels:99",
                provenance=AssetProvenance(
                    provider="pexels",
                    source_id="99",
                    license=LicenseState.STOCK_LICENSED.value,
                    stock=True,
                ),
                visual_information_id=viu.visual_information_id,
            )
        ],
    )
    payload = manifest.to_dict()
    assert payload["schema_version"] == "1"
    assert payload["beat_telemetry"][0]["beat_id"] == beat.beat_id
    assert payload["shot_telemetry"][0]["beat_id"] == beat.beat_id
    assert payload["shot_telemetry"][0]["asset_id"] == "asset:pexels:99"
    assert (
        payload["visual_information_units"][0]["visual_information_id"]
        == viu.visual_information_id
    )
    assert payload["model_calls"][0]["estimated_cost"] == 0.001
    assert payload["quality"][0]["reason_codes"] == ["domain_lock_ok"]


def test_ids_joinable_across_telemetry():
    job_id = "join-job"
    video_id = job_id
    m = build_production_manifest_from_legacy(
        job_id=job_id,
        topic="Test",
        script_data={
            "script": "hello",
            "script_quality": {"claims": [{"claim_id": "c1", "text": "x"}]},
        },
        quality={
            "word_to_visual": [
                {
                    "spoken_span": "hello",
                    "narrative_role": "HOOK",
                    "semantic_domain": "test",
                    "start_time": 0.0,
                    "end_time": 2.0,
                    "selected_asset": {
                        "asset_id": 42,
                        "provider": "pexels",
                        "kind": "video",
                        "path": "/tmp/a.mp4",
                        "metadata": {"license": ""},
                    },
                }
            ]
        },
        audio_duration=2.0,
    )
    assert m.job_id == m.video_id == video_id
    assert m.beats[0].beat_id.startswith(f"beat:{job_id}:")
    assert m.shot_telemetry[0].beat_id == m.beats[0].beat_id
    assert m.shot_telemetry[0].job_id == job_id
    assert m.shot_telemetry[0].video_id == video_id
    assert m.assets[0].provenance.license == LicenseState.UNKNOWN.value
    assert m.documentary_engine_v2 is False
    assert m.pipeline_mode == PipelineMode.LEGACY_STOCK.value


def test_adapter_preserves_unknown_license_and_synthetic():
    m = build_production_manifest_from_legacy(
        job_id="j2",
        topic="T",
        quality={
            "word_to_visual": [
                {
                    "provider": "ai_image",
                    "kind": "ai_image",
                    "asset_id": "gen1",
                    "path": "/tmp/x.png",
                    "selected_asset": {
                        "asset_id": "gen1",
                        "provider": "ai_image",
                        "kind": "ai_image",
                        "path": "/tmp/x.png",
                        "metadata": {},
                    },
                }
            ]
        },
    )
    assert m.assets[0].provenance.synthetic is True
    assert m.assets[0].provenance.license == "UNKNOWN"
    assert m.shot_telemetry[0].synthetic is True


def test_beat_shot_timestamps_mappable():
    m = build_production_manifest_from_legacy(
        job_id="ts1",
        topic="T",
        quality={
            "word_to_visual": [
                {
                    "start_time": 8.0,
                    "end_time": 9.2,
                    "narrative_role": "REVEAL",
                    "semantic_domain": "ownership",
                    "selected_asset": {
                        "asset_id": 1,
                        "provider": "pexels",
                        "kind": "video",
                        "path": "a.mp4",
                        "metadata": {"license": "STOCK_LICENSED"},
                    },
                }
            ]
        },
    )
    assert m.beat_telemetry[0].start_time == 8.0
    assert m.shot_telemetry[0].start_time == 8.0
    assert m.beat_telemetry[0].beat_id == m.shot_telemetry[0].beat_id


def test_model_call_cost_fields_serialize():
    mc = model_call_from_airouter(
        {
            "stage": "script_quality",
            "provider": "airouter",
            "model": "gemini-flash",
            "latency_ms": 250,
            "input_tokens": 800,
            "output_tokens": 200,
            "estimated_cost": 0.0025,
            "fallback_depth": 1,
            "status": "ok",
            "api_key": "SHOULD_NOT_APPEAR_IN_SCHEMA",
        },
        job_id="j",
        video_id="j",
    )
    d = mc.to_dict()
    assert d["estimated_cost"] == 0.0025
    assert d["fallback_depth"] == 1
    assert "api_key" not in d


def test_quality_telemetry_reason_codes():
    m = build_production_manifest_from_legacy(
        job_id="q1",
        topic="T",
        quality={
            "story_consistency": {"status": "FAIL", "reasons": ["domain_drift"]},
            "no_slideshow_gate": {
                "status": "FAIL",
                "reasons": ["unique_sources_below_min"],
            },
            "review_required": True,
            "review_reason": "fact_check_partial",
            "script_quality": {},
        },
    )
    gates = {q.gate: q for q in m.quality}
    assert gates["StoryConsistencyGate"].reason_codes == ["domain_drift"]
    assert gates["NoSlideshowQualityGate"].result == "FAIL"
    assert "FactQualityGate" in gates
    assert "FinalVideoQualityGate" not in gates
    assert "VisualCoverageGate" not in gates


def test_no_secret_leakage_in_manifest():
    m = ProductionManifest(
        job_id="sec",
        video_id="sec",
        quality=[
            QualityTelemetry(
                gate="x",
                details={"note": "ok"},
                job_id="sec",
                video_id="sec",
            )
        ],
    )
    payload = m.to_dict()
    payload["quality"][0]["details"]["api_key"] = "sk-test"
    leaks = ProductionManifest.assert_no_secrets(payload)
    assert any("api_key" in x for x in leaks)


def test_write_manifest_redacts_secrets(tmp_path: Path):
    class _Leaky(ProductionManifest):
        def to_dict(self):
            d = super().to_dict()
            d["access_token"] = "leak"
            return d

    path = write_production_manifest(tmp_path, _Leaky(job_id="w1", video_id="w1"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("access_token") == "[REDACTED]"


def test_flag_off_preserves_pending_path_semantics():
    """Stage A must not change approval state machine — only schema helpers."""
    from app import jobs as job_store

    assert "awaiting_approval" in job_store.JOB_STATES
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK
    assert documentary_engine_v2_enabled() is False


def test_example_production_manifest_join_chain(tmp_path: Path):
    """Demo: video → beat → shot → asset → VIU joinable for future MİKO."""
    job_id = "demo-20260924-stage-a"
    video_id = job_id
    beat_id = f"beat:{job_id}:0"
    shot_id = f"shot:{job_id}:0"
    asset_id = "asset:pexels:778899"
    viu_id = f"viu:{job_id}:0"
    manifest = ProductionManifest(
        job_id=job_id,
        video_id=video_id,
        topic="How Rolex Daytona became a status symbol",
        duration_sec=42.0,
        created_at="2026-09-24T16:00:00Z",
        pipeline_mode=PipelineMode.LEGACY_STOCK.value,
        documentary_engine_v2=False,
        pipeline_version="legacy",
        schema_version="1",
        beat_telemetry=[
            BeatTelemetry(
                beat_id=beat_id,
                job_id=job_id,
                video_id=video_id,
                start_time=8.4,
                end_time=12.1,
                narrative_role="REVEAL",
                semantic_domain="luxury_watch_ownership",
                claim_ids=["claim:daytona-paul-newman"],
                spoken_span="That watch was never meant for collectors.",
            )
        ],
        shot_telemetry=[
            ShotTelemetry(
                shot_id=shot_id,
                beat_id=beat_id,
                job_id=job_id,
                video_id=video_id,
                asset_id=asset_id,
                visual_information_id=viu_id,
                provider="pexels",
                media_type="stock_video",
                origin="stock",
                stock=True,
                license="STOCK_LICENSED",
                start_time=8.4,
                end_time=12.1,
                verification_status="NOT_RUN",
            )
        ],
        assets=[
            MediaAsset(
                asset_id=asset_id,
                provenance=AssetProvenance(
                    provider="pexels",
                    source_id="778899",
                    source_url="https://www.pexels.com/video/778899/",
                    media_type="stock_video",
                    license="STOCK_LICENSED",
                    stock=True,
                    synthetic=False,
                    retrieved_at="2026-09-24T16:00:00Z",
                ),
                visual_information_id=viu_id,
                origin="stock",
            )
        ],
        visual_information_units=[
            VisualInformationUnit(
                visual_information_id=viu_id,
                asset_id=asset_id,
                entity="Rolex Daytona",
                concept="wrist close-up",
                evidence_role="product_evidence",
                media_type="stock_video",
                beat_id=beat_id,
            )
        ],
        model_calls=[
            ModelCallTelemetry(
                call_id=f"mc:{job_id}:script",
                job_id=job_id,
                video_id=video_id,
                stage="script",
                provider="airouter",
                model="gemini-flash",
                latency_ms=410.0,
                input_tokens=1200,
                output_tokens=380,
                estimated_cost=0.0031,
                status="ok",
            )
        ],
        quality=[
            QualityTelemetry(
                gate="NoSlideshowQualityGate",
                result="FAIL",
                reason_codes=["unique_sources_below_min"],
                beat_ids=[beat_id],
                shot_ids=[shot_id],
                job_id=job_id,
                video_id=video_id,
            )
        ],
    )
    path = write_production_manifest(tmp_path, manifest)
    data = json.loads(path.read_text(encoding="utf-8"))
    bt = data["beat_telemetry"][0]
    st = data["shot_telemetry"][0]
    assert bt["start_time"] == 8.4
    assert st["start_time"] == 8.4
    assert st["beat_id"] == bt["beat_id"]
    assert st["asset_id"] == data["assets"][0]["asset_id"]
    assert (
        st["visual_information_id"]
        == data["visual_information_units"][0]["visual_information_id"]
    )
    assert data["documentary_engine_v2"] is False
    assert ProductionManifest.assert_no_secrets(data) == []
