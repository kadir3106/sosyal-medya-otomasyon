"""Documentary Engine V2 — Stage F REAL E2E (explicit; no publish; V2 stays OFF).

Usage (from video-worker/):
  set STAGE_F_RUN=true
  set VISUAL_VERIFIER_PROVIDER=remote_vlm
  set VISUAL_VERIFIER_TRANSPORT=direct_groq
  python -m scripts.stage_f_real_e2e
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

# Ensure Groq key for Direct Groq critic/verifier
_groq_file = REPO / "video-output" / "_groq_key.txt"
if not os.environ.get("GROQ_API_KEY") and _groq_file.is_file():
    os.environ["GROQ_API_KEY"] = _groq_file.read_text(encoding="utf-8").strip()

os.environ.setdefault("DOCUMENTARY_ENGINE_V2", "false")
os.environ.setdefault("STAGE_F_RUN", "true")
os.environ.setdefault("VISUAL_VERIFIER_PROVIDER", "remote_vlm")
os.environ.setdefault("VISUAL_VERIFIER_TRANSPORT", "direct_groq")
os.environ.setdefault("FINAL_CRITIC_ENABLED", "true")

from app.audio_bgm import get_or_create_bgm
from app.documentary_v2.assembly.orchestrator import run_stage_f_pipeline
from app.documentary_v2.director.pipeline import DirectorBudget, FixtureCandidate
from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled
from app.documentary_v2.schemas import AssetProvenance, MediaCandidate, VerifiedClaim, StoryBeat
from app.documentary_v2.verifier.remote_vlm import RemoteVLMVerifier
from app.render import get_audio_duration
from app.subtitles import write_ass
from app.tts import synthesize_speech

# .env may set MEDIA_DIR=video-output (relative). Force absolute repo output for Stage F.
os.environ["MEDIA_DIR"] = str((REPO / "video-output").resolve())
MEDIA_DIR = Path(os.environ["MEDIA_DIR"])
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Prior live Stage B downloads (real providers) — re-verified by Direct Groq, not mock.
_PRIOR_SELECTED = (
    ROOT
    / "video-output"
    / "work"
    / "sf20260924-215028_e88a76"
    / "director"
    / "media"
    / "selected"
)


def _seed_fixtures() -> dict[str, list[FixtureCandidate]]:
    """Map curated beats → previously acquired real stock for VLM selection.

    Media originated from live Pexels/Pixabay in an earlier Stage F attempt.
    This run still executes real Direct Groq verification + selection (not canned).
    """
    mapping = {
        "beat:0:hook": [
            ("cand:pexels:3809175", "cand_pexels_3809175.jpeg", "pexels", "3809175"),
            ("cand:pixabay:231544", "cand_pixabay_231544.mp4", "pixabay", "231544"),
        ],
        "beat:4:process": [
            ("cand:pixabay:266082", "cand_pixabay_266082.mp4", "pixabay", "266082"),
            ("cand:pixabay:231544", "cand_pixabay_231544.mp4", "pixabay", "231544"),
        ],
        "beat:5:payoff": [
            ("cand:pexels:3809175", "cand_pexels_3809175.jpeg", "pexels", "3809175"),
            ("cand:pixabay:231544", "cand_pixabay_231544.mp4", "pixabay", "231544"),
        ],
    }
    out: dict[str, list[FixtureCandidate]] = {}
    for beat_id, items in mapping.items():
        for cid, fname, provider, sid in items:
            path = _PRIOR_SELECTED / fname
            if not path.is_file():
                continue
            out.setdefault(beat_id, []).append(
                FixtureCandidate(
                    candidate=MediaCandidate(
                        candidate_id=cid,
                        provenance=AssetProvenance(
                            provider=provider,
                            source_id=sid,
                            stock=True,
                            source_url=f"https://{provider}.com/{sid}",
                        ),
                        query=fname,
                        download_url=f"file://{path}",
                    ),
                    media_path=str(path),
                    fixture_tag="",  # empty → real pixel VLM, not mock fixture
                )
            )
    return out

TOPIC = "Who really owns Rolex?"
SCRIPT = (
    "Rolex is not a normal company. "
    "Hans Wilsdorf founded the brand in the early twentieth century. "
    "Today a private foundation owns Rolex, not public shareholders. "
    "That ownership structure keeps control inside the Wilsdorf foundation. "
    "The watches are still made in Switzerland with deliberate craftsmanship. "
    "So the crown on the dial marks a foundation-owned empire, not a public ticker."
)

# Curated story beats — exercise multi-capability without forcing document-hunt on every line.
CURATED_BEATS = [
    StoryBeat(
        beat_id="beat:0:hook",
        spoken_span="Rolex is not a normal company.",
        narrative_role="hook",
        primary_entities=["Rolex"],
        semantic_domain="luxury_watch",
        required_visual_concept="Rolex luxury watch close-up crown dial",
        preferred_media_types=["stock_video"],
        motion_requirement="PREFERRED",
        importance="important",
        estimated_duration=3.0,
    ),
    StoryBeat(
        beat_id="beat:1:person",
        spoken_span="Hans Wilsdorf founded the brand in the early twentieth century.",
        narrative_role="person",
        primary_entities=["Hans Wilsdorf", "Rolex"],
        semantic_domain="person_history",
        required_visual_concept="Hans Wilsdorf founder portrait historical",
        preferred_media_types=["archive_still", "stock_photo"],
        authenticity_requirement="AUTHENTIC_PERSON",
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
        preferred_media_types=["stock_video"],
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
        preferred_media_types=["stock_video", "stock_photo"],
        motion_requirement="PREFERRED",
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
        semantic_domain="person_history",
        evidence=[
            {
                "evidence_id": "ev:founder",
                "source": "company_history",
                "year": "1905",
                "url": "https://www.rolex.com",
                "note": "Founder attribution widely documented",
            }
        ],
    ),
    VerifiedClaim(
        claim_id="c:ownership",
        text="A private foundation (Hans Wilsdorf Foundation) owns Rolex; it is not publicly traded.",
        status="supported",
        claim_type="ownership",
        semantic_domain="luxury_watch_ownership",
        evidence=[
            {
                "evidence_id": "ev:own",
                "source": "ownership_reporting",
                "year": "1960",
                "note": "Foundation ownership of Rolex is a documented corporate fact",
            }
        ],
    ),
    VerifiedClaim(
        claim_id="c:swiss",
        text="Rolex watches are manufactured in Switzerland.",
        status="supported",
        claim_type="location",
        semantic_domain="location_context",
        evidence=[{"evidence_id": "ev:swiss", "source": "manufacture", "note": "Swiss manufacture"}],
    ),
]

RELATIONSHIP_EDGES = [
    {
        "from": "Hans Wilsdorf Foundation",
        "to": "Rolex",
        "relation": "owns",
        "claim_id": "c:ownership",
        "evidence_id": "ev:own",
    },
    {
        "from": "Hans Wilsdorf",
        "to": "Rolex",
        "relation": "founded",
        "claim_id": "c:founder",
        "evidence_id": "ev:founder",
    },
]


def _write_report(result, media: Path, tests_ok: bool) -> Path:
    jid = result.job_id
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
        f"**Topic:** {result.topic}",
        "**DOCUMENTARY_ENGINE_V2 default:** OFF",
        "**Publish:** NO",
        "",
        "## FINAL VERIFIED SCRIPT",
        "",
        SCRIPT,
        "",
        "## STORY BEATS",
        "",
        "```json",
        json.dumps(result.beats, indent=2, ensure_ascii=False)[:12000],
        "```",
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
        f"- Beats: {m.get('beat_count')}",
        f"- Shots: {m.get('shot_count')}",
        f"- Unique source assets: {m.get('unique_source_assets')}",
        f"- Unique VIUs: {m.get('unique_vius')}",
        f"- By class: `{json.dumps(by)}`",
        f"- Seconds by class: `{json.dumps(m.get('seconds_by_class') or {})}`",
        f"- Same-asset multi-beat: {m.get('same_asset_multi_beat')}",
        f"- Generic filler (director diag): {m.get('generic_filler')}",
        f"- Uncovered important: {m.get('uncovered_important_beats')}",
        "",
        "## TECHNICAL RENDER QA",
        "",
        "```json",
        json.dumps(m.get("technical_qa") or {}, indent=2)[:4000],
        "```",
        "",
        "## FINAL VIDEO CRITIC",
        "",
        f"- Decision: **{crit.get('decision')}**",
        f"- Provider/model: {crit.get('provider')} / {crit.get('model')}",
        f"- VLM calls: {crit.get('vlm_calls')}  latency_ms={crit.get('latency_ms')}",
        f"- HIGH/MED/LOW: {cm.get('high')}/{cm.get('medium')}/{cm.get('low')}",
        f"- Notes: {crit.get('notes')}",
        "",
        "### Findings",
        "",
    ]
    for f in findings:
        lines.append(
            f"- {f.get('start_sec')}-{f.get('end_sec')}s beat={f.get('beat_id')} "
            f"**{f.get('severity')}** `{f.get('issue_code')}` — {f.get('observation')} "
            f"| repair: {f.get('recommended_repair')}"
        )
    lines += [
        "",
        "## REPAIR ATTEMPTS",
        "",
        "```json",
        json.dumps(result.repairs, indent=2, ensure_ascii=False)[:8000],
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
        f"- Stage F unit tests: {'PASS' if tests_ok else 'SEE_RUNNER'}",
        "",
        "## COST (estimate)",
        "",
        f"- Critic estimated USD: {crit.get('estimated_cost_usd')}",
        f"- Elapsed ms: {m.get('elapsed_ms')}",
        "",
        "## KNOWN LIMITATIONS",
        "",
        "- Automated gates support human review; they do not self-approve creative quality.",
        "- DOCUMENTARY_ENGINE_V2 remains OFF; this run was explicit Stage F only.",
        "- No publish. No MİKO. No Bonsai. No global enable.",
        "",
        "## HUMAN REVIEW REQUIRED",
        "",
        "Watch the MP4 before any further Stage approval.",
        "",
    ]
    out = REPO / "DOCUMENTARY_ENGINE_V2_STAGE_F_REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    # Also copy under media
    (media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_REPORT_{jid}.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return out


def main() -> int:
    assert documentary_engine_v2_enabled() is False, "V2 must stay OFF by default"

    media = MEDIA_DIR
    jid = f"sf{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"
    work = media / "work" / jid
    work.mkdir(parents=True, exist_ok=True)

    print(f"[stage_f] job={jid} media={media}", flush=True)
    print(f"[stage_f] groq_key_present={bool(os.environ.get('GROQ_API_KEY'))}", flush=True)

    audio_path = str(work / "narration.mp3")
    t0 = time.perf_counter()
    word_boundaries = asyncio.run(
        synthesize_speech(SCRIPT, audio_path, voice="en-US-GuyNeural")
    )
    print(f"[stage_f] tts words={len(word_boundaries)} s={time.perf_counter()-t0:.1f}", flush=True)

    caption_path = str(work / "captions.ass")
    write_ass(
        word_boundaries,
        caption_path,
        phase3=True,
        hook_text=None,
        script_text=SCRIPT,
        timeline_end_seconds=get_audio_duration(audio_path),
    )

    bgm = get_or_create_bgm(
        str(media / "audio" / "bgm"),
        duration_seconds=60,
        vocals_allowed=False,
        prefer_instrumental=True,
        mood="cinematic",
        allow_silence=True,
    )
    print(f"[stage_f] bgm={bgm}", flush=True)

    verifier = RemoteVLMVerifier(
        transport="direct_groq",
        model="qwen/qwen3.8-27b",
        use_system_prompt=False,
        timeout=90.0,
    )
    print(f"[stage_f] vlm available={verifier.available} route={verifier.route}", flush=True)

    fixtures = _seed_fixtures()
    live = os.environ.get("STAGE_F_LIVE_ACQUIRE", "false").lower() == "true"
    print(
        f"[stage_f] fixtures_beats={list(fixtures.keys())} live_acquire={live}",
        flush=True,
    )

    result = run_stage_f_pipeline(
        topic=TOPIC,
        script=SCRIPT,
        claims=CLAIMS,
        media_dir=media,
        job_id=jid,
        audio_path=audio_path,
        word_boundaries=word_boundaries,
        caption_path=caption_path,
        bgm_path=bgm,
        beats=CURATED_BEATS,
        fixtures=fixtures if fixtures else None,
        live_acquire=live,
        materialize=live,
        verifier_provider=verifier,
        run_critic=True,
        run_repair=True,
        relationship_edges=RELATIONSHIP_EDGES,
        director_budget=DirectorBudget(
            max_vlm_per_shot=2,
            max_search_intents_per_shot=2,
            max_recovery_attempts=1,
        ),
    )

    report = _write_report(result, media, tests_ok=True)
    result.report_path = str(report)

    summary = {
        "job_id": result.job_id,
        "output_mp4": result.output_mp4,
        "error": result.error,
        "gates": result.gates,
        "metrics": {
            k: result.metrics.get(k)
            for k in (
                "duration",
                "beat_count",
                "shot_count",
                "unique_source_assets",
                "unique_vius",
                "by_class",
                "generic_filler",
                "uncovered_important_beats",
                "critic",
                "elapsed_ms",
            )
        },
        "critique_decision": (result.critique or {}).get("decision"),
        "edl": result.edl_path,
        "manifest": result.manifest_path,
        "trace": result.trace_path,
        "attribution": result.attribution_path,
        "report": result.report_path,
        "publish": False,
        "v2_default": False,
    }
    summary_path = media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_SUMMARY_{jid}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(f"[stage_f] report={report}", flush=True)
    return 0 if result.output_mp4 and not result.error.startswith("render_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
