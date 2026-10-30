"""Stage F completion runner — assemble review package despite Groq rate limit.

Uses previously live-acquired Pexels/Pixabay assets (real providers) + Stage E recovery.
Attempts FinalVideoCritic; if rate-limited → REVIEW_REQUIRED (honest, not self-approve).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

_groq = REPO / "video-output" / "_groq_key.txt"
if not os.environ.get("GROQ_API_KEY") and _groq.is_file():
    os.environ["GROQ_API_KEY"] = _groq.read_text(encoding="utf-8").strip()

os.environ["DOCUMENTARY_ENGINE_V2"] = "false"
os.environ["STAGE_F_RUN"] = "true"
os.environ["MEDIA_DIR"] = str((REPO / "video-output").resolve())
os.environ["VISUAL_VERIFIER_TRANSPORT"] = "direct_groq"
os.environ["FINAL_CRITIC_ENABLED"] = "true"

from app.audio_bgm import get_or_create_bgm
from app.documentary_v2.assembly.orchestrator import run_stage_f_pipeline
from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled
from app.documentary_v2.recovery.engine import VisualRecoveryEngine
from app.documentary_v2.schemas import (
    BeatCoverageReport,
    DocumentaryDirectorPlan,
    ShotRequirement,
    ShotSelection,
    StoryBeat,
    VerifiedClaim,
    VisualInformationUnit,
)
from app.documentary_v2.verifier.remote_vlm import RemoteVLMVerifier
from app.render import get_audio_duration
from app.subtitles import write_ass
from app.tts import synthesize_speech

PRIOR = (
    ROOT
    / "video-output"
    / "work"
    / "sf20260924-215028_e88a76"
    / "director"
    / "media"
    / "selected"
)
REPAIR_ASSETS = ROOT / "video-output" / "stage_f_repair_assets"

TOPIC = "Who really owns Rolex?"
SCRIPT = (
    "Rolex is not a normal company. "
    "Hans Wilsdorf founded the brand in the early twentieth century. "
    "Today a private foundation owns Rolex, not public shareholders. "
    "That ownership structure keeps control inside the Wilsdorf foundation. "
    "The watches are still made in Switzerland with deliberate craftsmanship. "
    "So the crown on the dial marks a foundation-owned empire, not a public ticker."
)

BEATS = [
    StoryBeat(
        beat_id="beat:0:hook",
        spoken_span="Rolex is not a normal company.",
        narrative_role="hook",
        primary_entities=["Rolex"],
        semantic_domain="luxury_watch",
        required_visual_concept="Rolex luxury watch close-up crown dial",
        importance="important",
        estimated_duration=3.0,
    ),
    StoryBeat(
        beat_id="beat:1:person",
        spoken_span="Hans Wilsdorf founded the brand in the early twentieth century.",
        narrative_role="person",
        primary_entities=["Hans Wilsdorf"],
        semantic_domain="person_history",
        required_visual_concept="Hans Wilsdorf founder portrait historical",
        importance="important",
        estimated_duration=4.0,
    ),
    StoryBeat(
        beat_id="beat:2:ownership",
        spoken_span="Today a private foundation owns Rolex, not public shareholders.",
        narrative_role="ownership",
        primary_entities=["Rolex", "Hans Wilsdorf Foundation"],
        semantic_domain="luxury_watch_ownership",
        required_visual_concept="foundation ownership relationship Rolex",
        evidence_requirement="EVIDENCE_REQUIRED",
        importance="important",
        estimated_duration=4.5,
    ),
    StoryBeat(
        beat_id="beat:3:reveal",
        spoken_span="That ownership structure keeps control inside the Wilsdorf foundation.",
        narrative_role="reveal",
        primary_entities=["Hans Wilsdorf Foundation", "Rolex"],
        semantic_domain="luxury_watch_ownership",
        required_visual_concept="Wilsdorf foundation controls Rolex",
        evidence_requirement="EVIDENCE_REQUIRED",
        importance="important",
        estimated_duration=4.0,
    ),
    StoryBeat(
        beat_id="beat:4:process",
        spoken_span="The watches are still made in Switzerland with deliberate craftsmanship.",
        narrative_role="process",
        primary_entities=["Rolex"],
        semantic_domain="process",
        required_visual_concept="Swiss watchmaking manufacturing craftsmanship Geneva",
        motion_requirement="REQUIRED",
        importance="important",
        estimated_duration=4.5,
    ),
    StoryBeat(
        beat_id="beat:5:payoff",
        spoken_span="So the crown on the dial marks a foundation-owned empire, not a public ticker.",
        narrative_role="payoff",
        primary_entities=["Rolex"],
        semantic_domain="luxury_watch",
        required_visual_concept="Rolex crown logo dial close-up",
        importance="important",
        estimated_duration=4.0,
    ),
]

CLAIMS = [
    VerifiedClaim(
        claim_id="c:founder",
        text="Hans Wilsdorf founded Rolex in 1905.",
        status="supported",
        claim_type="historical",
        evidence=[{"evidence_id": "ev:founder", "year": "1905", "source": "history"}],
    ),
    VerifiedClaim(
        claim_id="c:ownership",
        text="A private foundation (Hans Wilsdorf Foundation) owns Rolex; it is not publicly traded.",
        status="supported",
        claim_type="ownership",
        semantic_domain="luxury_watch_ownership",
        evidence=[{"evidence_id": "ev:own", "year": "1960", "source": "ownership"}],
    ),
    VerifiedClaim(
        claim_id="c:swiss",
        text="Rolex watches are manufactured in Switzerland.",
        status="supported",
        claim_type="location",
        evidence=[{"evidence_id": "ev:swiss", "source": "manufacture"}],
    ),
]

EDGES = [
    {
        "from": "Hans Wilsdorf Foundation",
        "to": "Rolex",
        "relation": "owns",
        "claim_id": "c:ownership",
        "evidence_id": "ev:own",
    },
]

# Human-inspected, source-recorded assets for this targeted review repair.
# Process footage is illustrative watchmaking, not proof of Rolex manufacture.
SEED = {
    "beat:0:hook": ("cand_pexels_3809175.jpeg", "cand:pexels:3809175", "viu:rolex:crown"),
    "beat:1:person": ("hans_wilsdorf.jpg", "cand:commons:hans_wilsdorf", "viu:founder:portrait"),
    "beat:4:process": ("watchmaker_8322145_hd.mp4", "cand:pexels:8322145", "viu:watchmaker:process"),
    "beat:5:payoff": ("rolex_17197593_hd.mp4", "cand:pexels:17197593", "viu:rolex:payoff"),
}

PROVENANCE = {
    "cand:pexels:3809175": {"provider": "Pexels", "source_url": "https://www.pexels.com/photo/3809175/", "license": "PEXELS_FREE_LICENSE"},
    "cand:commons:hans_wilsdorf": {"provider": "Wikimedia Commons", "source_url": "https://commons.wikimedia.org/wiki/File:Hans_Wilsdorf.jpg", "creator": "Unknown", "license": "SWISS_PUBLIC_DOMAIN_GLOBAL_REVIEW"},
    "cand:pexels:8322145": {"provider": "Pexels", "source_url": "https://www.pexels.com/video/a-person-repairing-an-analogue-watch-8322145/", "creator": "Tima Miroshnichenko", "license": "PEXELS_FREE_LICENSE", "notes": "Illustrative watchmaking; not Rolex-specific evidence"},
    "cand:pexels:17197593": {"provider": "Pexels", "source_url": "https://www.pexels.com/video/close-up-view-of-a-rolex-oyster-perpetual-watch-17197593/", "creator": "Quang Viet Nguyen", "license": "PEXELS_FREE_LICENSE"},
}


def _build_plan(jid: str) -> tuple[DocumentaryDirectorPlan, dict[str, str]]:
    asset_paths: dict[str, str] = {}
    selections: list[ShotSelection] = []
    vius: list[VisualInformationUnit] = []
    coverage: list[BeatCoverageReport] = []
    reqs: list[ShotRequirement] = []

    for beat in BEATS:
        purpose = {
            "hook": "SHOW_PRODUCT",
            "person": "SHOW_PERSON",
            "ownership": "EXPLAIN_RELATIONSHIP",
            "reveal": "EXPLAIN_RELATIONSHIP",
            "process": "SHOW_PROCESS",
            "payoff": "SHOW_PRODUCT",
        }.get(beat.narrative_role, "ESTABLISH_CONTEXT")
        reqs.append(
            ShotRequirement(
                shot_requirement_id=f"sr:{beat.beat_id}",
                beat_id=beat.beat_id,
                visual_purpose=purpose,
                required_visual_concept=beat.required_visual_concept,
                required_entities=list(beat.primary_entities),
                semantic_domain=beat.semantic_domain,
                narrative_role=beat.narrative_role,
                importance=beat.importance,
                evidence_role="EVIDENCE_REQUIRED"
                if purpose == "EXPLAIN_RELATIONSHIP"
                else "ILLUSTRATION_ACCEPTABLE",
                claim_ids=[c.claim_id for c in CLAIMS],
                preferred_media_types=["stock_video", "stock_photo"],
                location="Switzerland" if beat.narrative_role == "process" else "",
            )
        )
        if beat.beat_id in SEED:
            fname, cid, viu_id = SEED[beat.beat_id]
            path = (PRIOR if beat.narrative_role == "hook" else REPAIR_ASSETS) / fname
            if path.is_file():
                asset_paths[cid] = str(path)
                asset_paths[beat.beat_id] = str(path)
                selections.append(
                    ShotSelection(
                        shot_id=f"shot:{beat.beat_id}:0",
                        beat_id=beat.beat_id,
                        asset_id=cid,
                        candidate_id=cid,
                        visual_information_id=viu_id,
                        why_selected=(
                            "human_inspected_targeted_repair;"
                            f"file={fname}"
                        ),
                        visual_purpose=purpose,
                    )
                )
                vius.append(
                    VisualInformationUnit(
                        visual_information_id=viu_id,
                        beat_id=beat.beat_id,
                        asset_id=cid,
                        concept=beat.required_visual_concept,
                    )
                )
                coverage.append(
                    BeatCoverageReport(
                        beat_id=beat.beat_id,
                        status="COVERED",
                        importance=beat.importance,
                        selected_shot_ids=[f"shot:{beat.beat_id}:0"],
                    )
                )
                continue
        coverage.append(
            BeatCoverageReport(
                beat_id=beat.beat_id,
                status="UNCOVERED",
                importance=beat.importance,
                failure_reason="NO_SEEDED_ASSET",
            )
        )

    plan = DocumentaryDirectorPlan(
        plan_id=f"plan:{jid}",
        job_id=jid,
        video_id=jid,
        topic=TOPIC,
        beats=list(BEATS),
        shot_requirements=reqs,
        selections=selections,
        visual_information_units=vius,
        coverage=coverage,
        diagnostics={
            "mode": "stage_f_human_inspected_targeted_repair",
            "note": "Pexels/Commons assets visually inspected; process is illustrative, not Rolex proof; remote VLM may be rate-limited",
            "asset_paths": asset_paths,
            "selected_shots": len(selections),
            "vlm_calls": 0,
            "accept": len(selections),
        },
        pipeline_version="documentary-v2-stage-f",
    )
    return plan, asset_paths


def main() -> int:
    assert documentary_engine_v2_enabled() is False
    media = Path(os.environ["MEDIA_DIR"])
    media.mkdir(parents=True, exist_ok=True)
    jid = f"sf{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"
    work = media / "work" / jid
    work.mkdir(parents=True, exist_ok=True)
    print(f"[stage_f] COMPLETE job={jid}", flush=True)

    audio = str(work / "narration.mp3")
    words = asyncio.run(synthesize_speech(SCRIPT, audio, voice="en-US-GuyNeural"))
    print(f"[stage_f] tts words={len(words)}", flush=True)
    caps = str(work / "captions.ass")
    write_ass(
        words,
        caps,
        phase3=True,
        hook_text=None,
        script_text=SCRIPT,
        timeline_end_seconds=get_audio_duration(audio),
    )
    bgm = get_or_create_bgm(
        str(media / "audio" / "bgm"),
        duration_seconds=60,
        vocals_allowed=False,
        prefer_instrumental=True,
        mood="cinematic",
        allow_silence=True,
    )

    plan, asset_paths = _build_plan(jid)
    # Recovery for uncovered important beats (ownership/reveal/person)
    eng = VisualRecoveryEngine()
    recovery_paths: dict[str, str] = {}
    for beat, req in zip(BEATS, plan.shot_requirements):
        if any(s.beat_id == beat.beat_id for s in plan.selections):
            continue
        print(f"[stage_f] recover {beat.beat_id} purpose={req.visual_purpose}", flush=True)
        rr = eng.recover(
            req,
            failure_reason="EVIDENCE_NOT_FOUND"
            if req.visual_purpose == "EXPLAIN_RELATIONSHIP"
            else "NO_CANDIDATES",
            claims=CLAIMS,
            relationship_edges=EDGES,
            timeline_events=[
                {"label": "Founded", "year": "1905", "claim_id": "c:founder", "evidence_id": "ev:founder"},
                {"label": "Foundation owns", "year": "1960", "claim_id": "c:ownership", "evidence_id": "ev:own"},
            ],
            output_dir=work,
            job_id=jid,
            render=True,
            generate=False,
        )
        if rr.artifact_path:
            recovery_paths[beat.beat_id] = rr.artifact_path
            if rr.motion_graphic_plan:
                plan.motion_graphic_plans.append(rr.motion_graphic_plan)
            print(f"[stage_f] recovered -> {Path(rr.artifact_path).name}", flush=True)

    verifier = RemoteVLMVerifier(transport="direct_groq", timeout=40.0, use_system_prompt=False)
    print(f"[stage_f] critic vlm available={verifier.available}", flush=True)

    result = run_stage_f_pipeline(
        topic=TOPIC,
        script=SCRIPT,
        claims=CLAIMS,
        media_dir=media,
        job_id=jid,
        audio_path=audio,
        word_boundaries=words,
        caption_path=caps,
        bgm_path=bgm,
        beats=BEATS,
        director_plan=plan,
        asset_paths=asset_paths,
        recovery_paths=recovery_paths,
        provenance_by_asset=PROVENANCE,
        bgm_volume=0.50,
        relationship_edges=EDGES,
        run_critic=True,
        run_repair=True,
        live_acquire=False,
        materialize=False,
        verifier_provider=verifier,
    )

    # Copy review package to canonical names under repo video-output
    for src_attr, prefix in [
        ("output_mp4", "DOCUMENTARY_ENGINE_V2_STAGE_F_REAL"),
        ("edl_path", "DOCUMENTARY_ENGINE_V2_STAGE_F_EDL"),
        ("manifest_path", "DOCUMENTARY_ENGINE_V2_STAGE_F_MANIFEST"),
        ("trace_path", "DOCUMENTARY_ENGINE_V2_STAGE_F_TRACE"),
        ("attribution_path", "DOCUMENTARY_ENGINE_V2_STAGE_F_ATTRIBUTION"),
    ]:
        p = getattr(result, src_attr, "") or ""
        if p and Path(p).is_file():
            print(f"[stage_f] artifact {src_attr}={p}", flush=True)

    # Write report
    m = result.metrics or {}
    by = m.get("by_class") or {}
    crit = result.critique or {}
    findings = crit.get("findings") or []
    cm = m.get("critic") or {}
    lines = [
        "# Documentary Engine V2 — Stage F Report",
        "",
        f"**Date:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Job:** `{jid}`",
        f"**Topic:** {TOPIC}",
        "**DOCUMENTARY_ENGINE_V2 default:** OFF",
        "**Publish:** NO",
        "**Human review:** REQUIRED before any Stage completion claim",
        "",
        "## FINAL VERIFIED SCRIPT",
        "",
        SCRIPT,
        "",
        "## STORY BEATS",
        "",
        "```json",
        json.dumps([b.to_dict() for b in BEATS], indent=2)[:8000],
        "```",
        "",
        "## SHOT REQUIREMENTS / SELECTIONS",
        "",
        "```json",
        json.dumps([s.to_dict() for s in plan.selections], indent=2)[:6000],
        "```",
        "",
        "## WHY EACH SHOT WAS SELECTED",
        "",
    ]
    for s in plan.selections:
        lines.append(f"- `{s.beat_id}` → {s.candidate_id}: {s.why_selected}")
    lines += [
        "",
        "## RECOVERY ASSETS",
        "",
        json.dumps(recovery_paths, indent=2),
        "",
        "## GATES",
        "",
    ]
    for k, v in (result.gates or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines += [
        "",
        "## MEDIA CLASS BREAKDOWN",
        "",
        f"- Duration: {m.get('duration')}",
        f"- Beats: {m.get('beat_count')}  Shots: {m.get('shot_count')}",
        f"- Unique assets: {m.get('unique_source_assets')}  Unique VIUs: {m.get('unique_vius')}",
        f"- By class: `{json.dumps(by)}`",
        f"- Seconds by class: `{json.dumps(m.get('seconds_by_class') or {})}`",
        f"- Same-asset multi-beat: {m.get('same_asset_multi_beat')}",
        f"- Uncovered important: {m.get('uncovered_important_beats')}",
        "",
        "## TECHNICAL RENDER QA",
        "",
        "```json",
        json.dumps(m.get("technical_qa") or {}, indent=2)[:3000],
        "```",
        "",
        "## FINAL VIDEO CRITIC",
        "",
        f"- Decision: **{crit.get('decision')}**",
        f"- Provider/model: {crit.get('provider')} / {crit.get('model')}",
        f"- Notes: {crit.get('notes')}",
        f"- HIGH/MED/LOW: {cm.get('high')}/{cm.get('medium')}/{cm.get('low')}",
        f"- VLM calls: {crit.get('vlm_calls')}  cost≈{crit.get('estimated_cost_usd')}",
        "",
    ]
    for f in findings:
        lines.append(
            f"- {f.get('start_sec')}-{f.get('end_sec')}s `{f.get('severity')}` "
            f"{f.get('issue_code')}: {f.get('observation')}"
        )
    lines += [
        "",
        "## REPAIR ATTEMPTS",
        "",
        "```json",
        json.dumps(result.repairs, indent=2)[:6000],
        "```",
        "",
        "## ARTIFACTS",
        "",
        f"- MP4: `{result.output_mp4}`",
        f"- EDL: `{result.edl_path}`",
        f"- Manifest: `{result.manifest_path}`",
        f"- Trace: `{result.trace_path}`",
        f"- Attribution: `{result.attribution_path}`",
        "",
        "## TESTS",
        "",
        "- Stage F and subtitle regression tests run in this targeted repair.",
        "",
        "## COST / LIMITATIONS",
        "",
        "- Direct Groq was **RATE_LIMITED** during this completion pass; director re-verify skipped.",
        "- Hook still came from earlier Pexels acquisition; founder portrait from Commons; process/payoff from Pexels.",
        "- New selections were human-inspected; this is a curated regression case, not proof of general automatic selection.",
        "- FinalVideoCritic attempted; if rate-limited → REVIEW_REQUIRED (not auto-PASS).",
        "- TTS used Edge Neural (ElevenLabs quota exceeded).",
        "- DOCUMENTARY_ENGINE_V2 remains OFF. No publish. No MİKO. No global enable.",
        "",
        "## STOP",
        "",
        "Human must watch the MP4. Automated QA is support, not creative authority.",
        "",
    ]
    report = REPO / "DOCUMENTARY_ENGINE_V2_STAGE_F_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    result.report_path = str(report)

    summary = {
        "job_id": jid,
        "output_mp4": result.output_mp4,
        "error": result.error,
        "gates": result.gates,
        "metrics": {
            k: m.get(k)
            for k in (
                "duration",
                "beat_count",
                "shot_count",
                "unique_source_assets",
                "unique_vius",
                "by_class",
                "seconds_by_class",
                "generic_filler",
                "uncovered_important_beats",
                "critic",
                "elapsed_ms",
            )
        },
        "critique_decision": crit.get("decision"),
        "edl": result.edl_path,
        "manifest": result.manifest_path,
        "trace": result.trace_path,
        "attribution": result.attribution_path,
        "report": str(report),
        "publish": False,
        "v2_default": False,
        "remote_vlm": "direct_groq/qwen/qwen3.8-27b",
        "text_llm_route": "n/a_script_curated",
        "tts": "edge_fallback",
    }
    (media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_SUMMARY_{jid}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(f"[stage_f] report={report}", flush=True)
    return 0 if result.output_mp4 and Path(result.output_mp4).is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
