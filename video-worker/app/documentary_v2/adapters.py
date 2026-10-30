"""Legacy → V2 compatibility adapters (Stage A).

Convert existing pipeline dictionaries into canonical schemas without
changing production behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.documentary_v2.schemas import (
    PIPELINE_VERSION_LEGACY,
    SCHEMA_VERSION,
    AssetProvenance,
    BeatTelemetry,
    LicenseState,
    MediaAsset,
    MediaType,
    ModelCallTelemetry,
    ProductionManifest,
    QualityTelemetry,
    RenderTelemetry,
    ShotSelection,
    ShotTelemetry,
    StoryBeat,
    VerifiedClaim,
    VerifiedStory,
    VisualInformationUnit,
    GateResult,
)
from app.documentary_v2.pipeline_mode import (
    documentary_engine_v2_enabled,
    resolve_pipeline_mode,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_video_id(job_id: str) -> str:
    """video_id == job_id for Stage A joinability (single production unit)."""
    return job_id


def claim_from_script_quality(d: dict) -> VerifiedClaim:
    return VerifiedClaim(
        claim_id=str(d.get("claim_id") or d.get("id") or ""),
        text=str(d.get("text") or d.get("original") or ""),
        claim_type=str(d.get("claim_type") or d.get("type") or ""),
        risk=str(d.get("risk") or ""),
        status=str(d.get("status") or d.get("evidence_status") or "unknown"),
        evidence=list(d.get("sources") or d.get("evidence") or []),
        narrative_role=str(d.get("narrative_role") or ""),
        semantic_domain=str(d.get("semantic_domain") or ""),
    )


def story_from_script_payload(
    *,
    job_id: str,
    topic: str,
    script_data: dict,
    quality: dict | None = None,
) -> VerifiedStory:
    quality = quality or {}
    sq = (script_data or {}).get("script_quality") or quality.get("script_quality") or {}
    hook = (
        script_data.get("hook")
        or sq.get("hook")
        or quality.get("hook")
        or ""
    )
    est = sq.get("estimated_duration")
    if est is None:
        est = quality.get("estimated_duration")
    return VerifiedStory(
        story_id=f"story:{job_id}",
        topic=topic,
        raw_script=str(script_data.get("raw_script") or ""),
        final_script=str(
            script_data.get("final_script")
            or script_data.get("script")
            or ""
        ),
        hook=str(hook),
        claim_ids=[
            str(c.get("claim_id") or "")
            for c in (sq.get("claims") or [])
            if c.get("claim_id")
        ],
        estimated_duration_sec=float(est) if est is not None else None,
    )


def model_call_from_airouter(
    d: dict,
    *,
    job_id: str,
    video_id: str,
    call_id: str = "",
) -> ModelCallTelemetry:
    """Map AIRouter-shaped telemetry dicts — no secrets, no AIRouter redesign."""
    return ModelCallTelemetry(
        call_id=call_id or str(d.get("call_id") or f"mc:{job_id}:{d.get('stage', 'x')}"),
        job_id=job_id,
        video_id=video_id,
        stage=str(d.get("stage") or ""),
        provider=str(d.get("provider") or ""),
        model=str(d.get("model") or ""),
        latency_ms=float(d["latency_ms"]) if d.get("latency_ms") is not None else None,
        input_tokens=int(d["input_tokens"]) if d.get("input_tokens") is not None else None,
        output_tokens=int(d["output_tokens"]) if d.get("output_tokens") is not None else None,
        estimated_cost=float(d["estimated_cost"]) if d.get("estimated_cost") is not None else None,
        fallback_depth=int(d.get("fallback_depth") or 0),
        status=str(d.get("status") or ""),
    )


def beats_from_word_to_visual(
    word_to_visual: list[dict],
    *,
    job_id: str,
    audio_duration: float | None = None,
) -> list[StoryBeat]:
    beats: list[StoryBeat] = []
    t = 0.0
    n = max(len(word_to_visual or []), 1)
    default_dur = (float(audio_duration) / n) if audio_duration else 2.0
    for i, b in enumerate(word_to_visual or []):
        dur = float(b.get("duration") or b.get("resolved_duration") or default_dur)
        start = float(b.get("start_time") if b.get("start_time") is not None else t)
        end = float(b.get("end_time") if b.get("end_time") is not None else start + dur)
        beat_id = str(b.get("beat") if b.get("beat") is not None else i)
        if not beat_id.startswith("beat:"):
            beat_id = f"beat:{job_id}:{beat_id}"
        beats.append(
            StoryBeat(
                beat_id=beat_id,
                spoken_span=str(b.get("spoken_span") or ""),
                narrative_role=str(b.get("narrative_role") or ""),
                primary_entities=list(b.get("primary_entities") or b.get("entities") or []),
                semantic_domain=str(b.get("semantic_domain") or ""),
                required_visual_concept=str(
                    b.get("required_visual_concept") or b.get("concept") or ""
                ),
                evidence_requirement=str(b.get("evidence_role") or ""),
                estimated_duration=dur,
                start_time=start,
                end_time=end,
            )
        )
        t = end
    return beats


def asset_from_word_to_visual_row(b: dict, *, job_id: str, index: int) -> MediaAsset | None:
    sel = b.get("selected_asset") or {}
    aid = sel.get("asset_id") if sel.get("asset_id") is not None else b.get("asset_id")
    path = str(sel.get("path") or b.get("path") or "")
    if aid is None and not path:
        return None
    provider = str(sel.get("provider") or b.get("provider") or "")
    kind = str(sel.get("kind") or b.get("kind") or b.get("media_kind") or "")
    meta = sel.get("metadata") or {}
    synthetic = kind in {"ai_image", "motion_graphic"} or provider in {
        "ai_image",
        "motion_graphic",
    }
    archive = bool(b.get("person_archive")) or "archive" in str(
        b.get("evidence_role") or ""
    ).lower() or provider.startswith("wikipedia")
    stock = not synthetic and not archive
    lic = meta.get("license") or LicenseState.UNKNOWN.value
    if not str(lic).strip():
        lic = LicenseState.UNKNOWN.value
    asset_id = f"asset:{provider}:{aid}" if aid is not None else f"asset:{job_id}:{index}"
    prov = AssetProvenance(
        provider=provider,
        source_id=str(aid) if aid is not None else "",
        source_url=str(meta.get("url") or meta.get("page_url") or b.get("url") or ""),
        download_url=str(meta.get("download_url") or ""),
        preview_url=str(meta.get("preview_url") or ""),
        media_type=kind or MediaType.OTHER.value,
        creator=str(meta.get("user") or meta.get("photographer") or ""),
        license=str(lic),
        attribution=str(meta.get("attribution") or ""),
        synthetic=synthetic,
        archive=archive,
        stock=stock,
        content_fingerprint=str(b.get("content_fingerprint") or ""),
        retrieved_at=_utc_now(),
    )
    return MediaAsset(
        asset_id=asset_id,
        provenance=prov,
        local_path=path,
        origin=(
            "generated"
            if synthetic and provider != "motion_graphic"
            else (
                "motion_graphic"
                if provider == "motion_graphic" or kind == "motion_graphic"
                else ("archive" if archive else "stock")
            )
        ),
        visual_information_id=str(b.get("visual_information_id") or ""),
    )


def viu_from_dict(d: dict, *, job_id: str, index: int) -> VisualInformationUnit:
    vid = str(d.get("id") or d.get("visual_information_id") or f"viu:{job_id}:{index}")
    return VisualInformationUnit(
        visual_information_id=vid,
        asset_id=str(d.get("source_asset_id") or d.get("asset_id") or ""),
        entity=str(d.get("entity") or ""),
        concept=str(d.get("concept") or ""),
        action=str(d.get("action") or ""),
        evidence_role=str(d.get("evidence_role") or ""),
        media_type=str(d.get("media_type") or ""),
        authenticity=str(d.get("authenticity") or ""),
        beat_id=str(d.get("beat_id") if d.get("beat_id") is not None else ""),
    )


def quality_from_existing(quality: dict, *, job_id: str, video_id: str) -> list[QualityTelemetry]:
    """Map gates that actually ran — never invent NOT_RUN as PASS."""
    out: list[QualityTelemetry] = []
    sc = quality.get("story_consistency") or {}
    if sc:
        out.append(
            QualityTelemetry(
                gate="StoryConsistencyGate",
                result=str(sc.get("status") or GateResult.NOT_RUN.value),
                reason_codes=list(sc.get("reasons") or []),
                job_id=job_id,
                video_id=video_id,
                details=sc if isinstance(sc, dict) else {},
            )
        )
    nsg = quality.get("no_slideshow_gate") or {}
    if nsg:
        out.append(
            QualityTelemetry(
                gate="NoSlideshowQualityGate",
                result=str(nsg.get("status") or GateResult.NOT_RUN.value),
                reason_codes=list(nsg.get("reasons") or []),
                job_id=job_id,
                video_id=video_id,
                details={"diagnostics": nsg.get("diagnostics")} if isinstance(nsg, dict) else {},
            )
        )
    sq = quality.get("script_quality") or {}
    if sq or quality.get("review_reason"):
        result = GateResult.REVIEW_REQUIRED.value if quality.get("review_required") else GateResult.PASS.value
        reasons = []
        if quality.get("review_reason"):
            reasons.append(str(quality.get("review_reason")))
        out.append(
            QualityTelemetry(
                gate="FactQualityGate",
                result=result,
                reason_codes=reasons,
                job_id=job_id,
                video_id=video_id,
                details={
                    "verification_summary": (sq.get("verification_summary") if isinstance(sq, dict) else None)
                },
            )
        )
    # Do not invent VisualCoverage / License / FinalVideo gates as PASS
    return out


def build_production_manifest_from_legacy(
    *,
    job_id: str,
    topic: str,
    script_data: dict | None = None,
    quality: dict | None = None,
    result: dict | None = None,
    audio_duration: float | None = None,
) -> ProductionManifest:
    """Adapter: existing pipeline outputs → ProductionManifest."""
    script_data = script_data or {}
    quality = quality or (result or {}).get("quality") or {}
    video_id = _stable_video_id(job_id)
    mode = resolve_pipeline_mode()
    w2v = quality.get("word_to_visual") or []
    beats = beats_from_word_to_visual(w2v, job_id=job_id, audio_duration=audio_duration)
    assets: list[MediaAsset] = []
    shots: list[ShotSelection] = []
    shot_tel: list[ShotTelemetry] = []
    beat_tel: list[BeatTelemetry] = []
    reuse: dict[str, int] = {}

    for i, b in enumerate(w2v):
        asset = asset_from_word_to_visual_row(b, job_id=job_id, index=i)
        beat_id = beats[i].beat_id if i < len(beats) else f"beat:{job_id}:{i}"
        if i < len(beats):
            beat_tel.append(
                BeatTelemetry(
                    beat_id=beat_id,
                    job_id=job_id,
                    video_id=video_id,
                    start_time=beats[i].start_time,
                    end_time=beats[i].end_time,
                    narrative_role=beats[i].narrative_role,
                    semantic_domain=beats[i].semantic_domain,
                    entities=list(beats[i].primary_entities),
                    claim_ids=list(beats[i].claim_ids),
                    spoken_span=beats[i].spoken_span,
                )
            )
        if not asset:
            continue
        reuse[asset.asset_id] = reuse.get(asset.asset_id, 0) + 1
        assets.append(asset)
        shot_id = f"shot:{job_id}:{i}"
        shots.append(
            ShotSelection(
                shot_id=shot_id,
                beat_id=beat_id,
                asset_id=asset.asset_id,
                visual_information_id=asset.visual_information_id,
                start_time=beats[i].start_time if i < len(beats) else None,
                end_time=beats[i].end_time if i < len(beats) else None,
                selection_reason=str(b.get("gate_reason") or "legacy"),
            )
        )
        shot_tel.append(
            ShotTelemetry(
                shot_id=shot_id,
                beat_id=beat_id,
                job_id=job_id,
                video_id=video_id,
                asset_id=asset.asset_id,
                visual_information_id=asset.visual_information_id,
                provider=asset.provenance.provider,
                media_type=asset.provenance.media_type,
                origin=asset.origin,
                synthetic=asset.provenance.synthetic,
                archive=asset.provenance.archive,
                stock=asset.provenance.stock,
                license=asset.provenance.license or LicenseState.UNKNOWN.value,
                source_url=asset.provenance.source_url,
                start_time=beats[i].start_time if i < len(beats) else None,
                end_time=beats[i].end_time if i < len(beats) else None,
                reuse_count=reuse[asset.asset_id],
                verification_status="NOT_RUN",
            )
        )

    for st in shot_tel:
        st.reuse_count = reuse.get(st.asset_id, 1)

    vius = [
        viu_from_dict(v, job_id=job_id, index=i)
        for i, v in enumerate(quality.get("visual_information_units") or [])
    ]

    claims = [
        claim_from_script_quality(c)
        for c in ((script_data.get("script_quality") or {}).get("claims") or [])
    ]

    story = story_from_script_payload(
        job_id=job_id, topic=topic, script_data=script_data, quality=quality
    )

    dur = audio_duration
    if dur is None and result:
        # best-effort from quality
        dur = quality.get("estimated_duration")

    return ProductionManifest(
        job_id=job_id,
        video_id=video_id,
        topic=topic,
        duration_sec=float(dur) if dur is not None else None,
        created_at=_utc_now(),
        pipeline_mode=mode.value,
        documentary_engine_v2=documentary_engine_v2_enabled(),
        pipeline_version=PIPELINE_VERSION_LEGACY,
        schema_version=SCHEMA_VERSION,
        story=story,
        claims=claims,
        beats=beats,
        assets=assets,
        visual_information_units=vius,
        shot_selections=shots,
        beat_telemetry=beat_tel,
        shot_telemetry=shot_tel,
        quality=quality_from_existing(quality, job_id=job_id, video_id=video_id),
        render_telemetry=RenderTelemetry(
            job_id=job_id,
            video_id=video_id,
            duration_sec=float(dur) if dur is not None else None,
        ),
    )
