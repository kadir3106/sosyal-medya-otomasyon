"""FinalVideoCritic — judges ACTUAL rendered MP4 via Direct Groq vision batches."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.documentary_v2.schemas import (
    CriticFinding,
    DocumentaryDirectorPlan,
    EditDecisionList,
    FinalVideoCritique,
    PreviewFrame,
)
from app.documentary_v2.verifier.remote_vlm import RemoteVLMVerifier
from app.documentary_v2.verifier.sampler import build_preview_bundle


CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REVIEW_REQUIRED", "FAIL"]},
        "dimensions": {
            "type": "object",
            "properties": {
                "narration_visual_alignment": {"type": "string"},
                "entity_alignment": {"type": "string"},
                "story_progression": {"type": "string"},
                "generic_broll": {"type": "string"},
                "slideshow_feel": {"type": "string"},
                "evidence_representation": {"type": "string"},
                "synthetic_misrepresentation": {"type": "string"},
                "hook_clarity": {"type": "string"},
                "payoff_clarity": {"type": "string"},
                "visual_coherence": {"type": "string"},
            },
            "required": [
                "narration_visual_alignment",
                "entity_alignment",
                "story_progression",
                "generic_broll",
                "slideshow_feel",
                "evidence_representation",
                "synthetic_misrepresentation",
                "hook_clarity",
                "payoff_clarity",
                "visual_coherence",
            ],
            "additionalProperties": False,
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_sec": {"type": "number"},
                    "end_sec": {"type": "number"},
                    "beat_id": {"type": "string"},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "issue_code": {"type": "string"},
                    "observation": {"type": "string"},
                    "recommended_repair": {"type": "string"},
                },
                "required": [
                    "start_sec",
                    "end_sec",
                    "beat_id",
                    "severity",
                    "issue_code",
                    "observation",
                    "recommended_repair",
                ],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["decision", "dimensions", "findings", "summary"],
    "additionalProperties": False,
}

ISSUE_CODES = (
    "WRONG_ENTITY",
    "WRONG_VISUAL_CONCEPT",
    "UNSUPPORTED_EVIDENCE_VISUAL",
    "GENERIC_FILLER",
    "EXCESSIVE_ASSET_REUSE",
    "TRANSFORM_AS_FAKE_VARIETY",
    "SLIDESHOW_FEEL",
    "STATIC_HOLD_TOO_LONG",
    "MOTION_OPPORTUNITY_MISSED",
    "CAPTION_BLOCKS_SUBJECT",
    "GRAPHIC_UNREADABLE",
    "ABRUPT_VISUAL_DISCONTINUITY",
    "SYNTHETIC_LOOKS_LIKE_EVIDENCE",
    "WEAK_HOOK_VISUAL",
    "WEAK_PAYOFF",
    "AUDIO_VISUAL_TIMING_MISMATCH",
    "VISUAL_DOES_NOT_SUPPORT_CLAIM",
)


def _beat_context(plan: DocumentaryDirectorPlan, edl: EditDecisionList) -> str:
    lines = []
    for b in plan.beats or []:
        lines.append(
            f"- beat={b.beat_id} role={b.narrative_role} "
            f"concept={b.required_visual_concept} spoken={((b.spoken_span or '')[:100])}"
        )
    for d in edl.decisions or []:
        lines.append(
            f"- edit {d.start_time:.1f}-{d.end_time:.1f}s beat={d.beat_id} "
            f"purpose={d.visual_purpose} synthetic={d.synthetic} path={Path(d.local_path).name}"
        )
    return "\n".join(lines)


class FinalVideoCritic:
    """Inspect rendered MP4 pixels via Direct Groq (never AIRouter vision)."""

    def __init__(self, *, transport: str = "direct_groq") -> None:
        self.vlm = RemoteVLMVerifier(
            transport=transport,
            model="qwen/qwen3.8-27b",
            use_system_prompt=False,
            timeout=90.0,
        )

    def critique(
        self,
        video_path: str,
        *,
        plan: DocumentaryDirectorPlan,
        edl: EditDecisionList,
        story_text: str = "",
        work_dir: str | Path | None = None,
        max_frames: int = 6,
    ) -> FinalVideoCritique:
        t0 = time.perf_counter()
        cid = f"crit:{uuid.uuid4().hex[:12]}"
        if not self.vlm.available:
            return FinalVideoCritique(
                critique_id=cid,
                job_id=edl.job_id,
                video_path=video_path,
                decision="REVIEW_REQUIRED",
                notes="VLM_UNAVAILABLE: critic cannot run without Direct Groq credentials",
                provider="direct_groq",
            )

        bundle = build_preview_bundle(
            video_path,
            candidate_id=edl.video_id or "final",
            media_kind="video",
            max_frames=max_frames,
            work_dir=work_dir,
        )
        frames = [f for f in bundle.frames if f.path and Path(f.path).is_file()]
        if not frames:
            return FinalVideoCritique(
                critique_id=cid,
                job_id=edl.job_id,
                video_path=video_path,
                decision="FAIL",
                notes="no_preview_frames",
            )

        # Batch ≤3 images per request (Groq qwen limit)
        batches: list[list[PreviewFrame]] = []
        for i in range(0, len(frames), 3):
            batches.append(frames[i : i + 3])

        prompt_base = (
            "You are FinalVideoCritic for a short-form mini-documentary. "
            "Judge ONLY what is visible in the attached frames from the FINAL rendered video. "
            "Plans are context, not proof. "
            "Issue codes must be from the allowed list. "
            "Flag HIGH severity when important beats show wrong entity, generic filler, "
            "slideshow feel, fake evidence, or synthetic presented as archive. "
            "Return schema JSON only.\n\n"
            f"Story excerpt:\n{(story_text or '')[:800]}\n\n"
            f"Beat/edit context:\n{_beat_context(plan, edl)}\n\n"
            f"Allowed issue codes: {', '.join(ISSUE_CODES)}"
        )

        all_findings: list[CriticFinding] = []
        dimensions: dict = {}
        decision = "PASS"
        vlm_calls = 0
        summaries: list[str] = []

        for bi, batch in enumerate(batches):
            text = (
                prompt_base
                + f"\nBatch {bi + 1}/{len(batches)}. "
                f"Frame timestamps: {[f.timestamp_sec for f in batch]}"
            )
            try:
                data, meta = self.vlm.chat_structured(
                    text=text,
                    frames=batch,
                    schema=CRITIC_SCHEMA,
                    schema_name="final_video_critique",
                    strict=False,
                )
                vlm_calls += 1
            except Exception as exc:
                return FinalVideoCritique(
                    critique_id=cid,
                    job_id=edl.job_id,
                    video_path=video_path,
                    decision="REVIEW_REQUIRED",
                    notes=f"critic_vlm_error:{exc}"[:300],
                    vlm_calls=vlm_calls,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    provider=self.vlm.route,
                    model=self.vlm.model,
                )

            if isinstance(data.get("dimensions"), dict) and not dimensions:
                dimensions = data["dimensions"]
            summaries.append(str(data.get("summary") or ""))
            dec = str(data.get("decision") or "REVIEW_REQUIRED").upper()
            if dec == "FAIL":
                decision = "FAIL"
            elif dec == "REVIEW_REQUIRED" and decision != "FAIL":
                decision = "REVIEW_REQUIRED"
            for raw in data.get("findings") or []:
                code = str(raw.get("issue_code") or "WRONG_VISUAL_CONCEPT")
                if code not in ISSUE_CODES:
                    code = "WRONG_VISUAL_CONCEPT"
                all_findings.append(
                    CriticFinding(
                        finding_id=f"f:{uuid.uuid4().hex[:8]}",
                        start_sec=float(raw.get("start_sec") or 0),
                        end_sec=float(raw.get("end_sec") or 0),
                        beat_id=str(raw.get("beat_id") or ""),
                        severity=str(raw.get("severity") or "LOW").upper(),
                        issue_code=code,
                        observation=str(raw.get("observation") or "")[:400],
                        recommended_repair=str(raw.get("recommended_repair") or "")[:300],
                    )
                )

        # Escalate if any HIGH
        if any(f.severity == "HIGH" for f in all_findings) and decision == "PASS":
            decision = "REVIEW_REQUIRED"

        return FinalVideoCritique(
            critique_id=cid,
            job_id=edl.job_id,
            video_path=video_path,
            decision=decision,
            findings=all_findings,
            dimensions=dimensions,
            latency_ms=(time.perf_counter() - t0) * 1000,
            vlm_calls=vlm_calls,
            estimated_cost_usd=round(0.002 * vlm_calls, 4),
            model=self.vlm.model,
            provider=self.vlm.route,
            notes=" | ".join(summaries)[:500],
        )
