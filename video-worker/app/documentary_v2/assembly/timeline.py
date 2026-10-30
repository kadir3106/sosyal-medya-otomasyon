"""DocumentaryTimelineCompiler — narration clock → EditDecisionList."""
from __future__ import annotations

import uuid
import re
from pathlib import Path
from typing import Any

from app.documentary_v2.schemas import (
    DocumentaryDirectorPlan,
    EditDecision,
    EditDecisionList,
    ShotSelection,
    StoryBeat,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def _word_span_seconds(boundaries: list[dict]) -> tuple[float, float]:
    if not boundaries:
        return 0.0, 0.0
    start = boundaries[0]["offset"] / 10_000_000
    end = (boundaries[-1]["offset"] + boundaries[-1]["duration"]) / 10_000_000
    return float(start), float(end)


def _allocate_beat_windows(
    beats: list[StoryBeat],
    narration_duration: float,
    word_boundaries: list[dict] | None = None,
) -> list[tuple[float, float]]:
    """Map beats onto narration timeline using spoken length weights."""
    if not beats:
        return []
    if word_boundaries:
        norm = lambda value: re.sub(r"[^\w]", "", str(value).casefold())
        spoken = [norm(token) for beat in beats for token in beat.spoken_span.split()]
        heard = [norm(word.get("text", "")) for word in word_boundaries]
        if spoken == heard and all(spoken):
            starts = [0.0]
            count = 0
            for beat in beats[:-1]:
                count += len(beat.spoken_span.split())
                starts.append(word_boundaries[count]["offset"] / 10_000_000)
            _, spoken_end = _word_span_seconds(word_boundaries)
            final_end = max(float(narration_duration), spoken_end)
            return list(zip(starts, starts[1:] + [final_end]))
    n = len(beats)
    weights = []
    for b in beats:
        w = max(len((b.spoken_span or "").split()), 3)
        if b.estimated_duration:
            w = max(w, float(b.estimated_duration) * 4)
        weights.append(w)
    total_w = sum(weights) or 1.0
    # Prefer audio duration as clock
    dur = max(float(narration_duration), 1.0)
    if word_boundaries:
        _, end = _word_span_seconds(word_boundaries)
        if end > 0.5:
            dur = end
    windows: list[tuple[float, float]] = []
    t = 0.0
    for i, w in enumerate(weights):
        slice_dur = dur * (w / total_w)
        # Hook may be denser — allow shorter minimum; evidence longer
        role = (beats[i].narrative_role or "").lower()
        if "hook" in role:
            slice_dur = max(1.2, min(slice_dur, 4.0))
        elif "evidence" in role or "reveal" in role:
            slice_dur = max(2.0, slice_dur)
        else:
            slice_dur = max(1.4, slice_dur)
        end = t + slice_dur
        windows.append((t, end))
        t = end
    # Normalize last end to narration duration
    if windows:
        scale = dur / windows[-1][1] if windows[-1][1] > 0 else 1.0
        if abs(scale - 1.0) > 0.05:
            windows = [(a * scale, b * scale) for a, b in windows]
            windows[-1] = (windows[-1][0], dur)
    return windows


def _motion_policy_for(path: str, purpose: str, media_type: str, synthetic: bool) -> str:
    if _is_image(path) or "still" in (media_type or "").lower() or "photo" in (media_type or "").lower():
        # Subtle presentation only — never fake diversity
        if purpose in {"SHOW_PERSON", "SHOW_EVIDENCE"} or "document" in (media_type or "").lower():
            return "subtle_push"
        return "subtle_push"
    if synthetic or "motion_graphic" in (media_type or "").lower() or "graphic" in (path or "").lower():
        return "preserve_native"
    return "preserve_native"


def _split_beat_into_shots(
    beat_dur: float,
    selections: list[ShotSelection],
    *,
    narrative_role: str,
) -> list[tuple[ShotSelection, float]]:
    """One beat may yield multiple shots; durations sum to beat window."""
    if not selections:
        return []
    role = (narrative_role or "").lower()
    # Hook: allow up to 3 fast shots if multiple available
    max_shots = 3 if "hook" in role else (2 if "process" in role or "develop" in role else 1)
    chosen = selections[:max_shots]
    if len(chosen) == 1:
        return [(chosen[0], beat_dur)]
    # Weight: first shot slightly longer for hook payoff within beat
    weights = [1.2] + [1.0] * (len(chosen) - 1)
    tw = sum(weights)
    out = []
    for sel, w in zip(chosen, weights):
        out.append((sel, max(0.9, beat_dur * (w / tw))))
    # Fix rounding
    total = sum(d for _, d in out)
    if total > 0 and abs(total - beat_dur) > 0.01:
        scale = beat_dur / total
        out = [(s, d * scale) for s, d in out]
    return out


def compile_edl(
    plan: DocumentaryDirectorPlan,
    *,
    narration_duration_sec: float,
    word_boundaries: list[dict] | None = None,
    asset_paths: dict[str, str] | None = None,
    recovery_paths: dict[str, str] | None = None,
    job_id: str = "",
    video_id: str = "",
) -> EditDecisionList:
    """Compile spoken-aligned EDL. Renderer must not invent shot order."""
    asset_paths = asset_paths or {}
    recovery_paths = recovery_paths or {}
    beats = list(plan.beats or [])
    windows = _allocate_beat_windows(beats, narration_duration_sec, word_boundaries)

    # Index selections by beat
    by_beat: dict[str, list[ShotSelection]] = {}
    for sel in plan.selections or []:
        by_beat.setdefault(sel.beat_id, []).append(sel)

    # Recovery artifacts keyed by beat
    mg_by_beat = {p.beat_id: p for p in (plan.motion_graphic_plans or [])}
    gen_by_beat = {p.beat_id: p for p in (plan.generated_visual_plans or [])}

    decisions: list[EditDecision] = []
    notes: list[str] = []
    t_cursor = 0.0

    for i, beat in enumerate(beats):
        b_start, b_end = windows[i] if i < len(windows) else (t_cursor, t_cursor + 2.0)
        beat_dur = max(0.8, b_end - b_start)
        sels = by_beat.get(beat.beat_id, [])

        # Prefer verified selections; else recovery path if available
        shot_slots: list[tuple[str, str, str, str, bool, str, str, float]] = []
        # tuple: path, asset_id, viu, media_type, synthetic, purpose, evidence_role, dur

        if sels:
            for sel, dur in _split_beat_into_shots(
                beat_dur, sels, narrative_role=beat.narrative_role
            ):
                path = (
                    asset_paths.get(sel.candidate_id)
                    or asset_paths.get(sel.asset_id)
                    or asset_paths.get(beat.beat_id)
                    or asset_paths.get(f"beat:{beat.beat_id}")
                    or recovery_paths.get(sel.beat_id)
                    or ""
                )
                if not path or not Path(path).is_file():
                    notes.append(f"missing_path:{sel.candidate_id}")
                    continue
                shot_slots.append(
                    (
                        path,
                        sel.asset_id or sel.candidate_id,
                        sel.visual_information_id,
                        "stock_video" if not _is_image(path) else "archive_still",
                        False,
                        getattr(sel, "visual_purpose", "") or "",
                        "",
                        dur,
                    )
                )
        else:
            # Recovery asset for uncovered beat
            rpath = recovery_paths.get(beat.beat_id, "")
            mg = mg_by_beat.get(beat.beat_id)
            gen = gen_by_beat.get(beat.beat_id)
            if rpath and Path(rpath).is_file():
                synthetic = bool(gen) or (mg is not None)
                media = "motion_graphic" if mg else ("generated_video" if gen else "recovery")
                shot_slots.append(
                    (
                        rpath,
                        f"recovery:{beat.beat_id}",
                        f"viu:recovery:{beat.beat_id}",
                        media,
                        synthetic,
                        "EXPLAIN_RELATIONSHIP" if mg else "ESTABLISH_CONTEXT",
                        "EXPLANATORY" if mg else "ILLUSTRATION",
                        beat_dur,
                    )
                )
            else:
                notes.append(f"uncovered_no_asset:{beat.beat_id}")

        # If selection paths failed but recovery exists, use recovery as backup
        if not shot_slots:
            rpath = recovery_paths.get(beat.beat_id, "")
            if rpath and Path(rpath).is_file():
                mg = mg_by_beat.get(beat.beat_id)
                shot_slots.append(
                    (
                        rpath,
                        f"recovery:{beat.beat_id}",
                        f"viu:recovery:{beat.beat_id}",
                        "motion_graphic" if mg else "recovery",
                        True,
                        "EXPLAIN_RELATIONSHIP" if mg else "ESTABLISH_CONTEXT",
                        "EXPLANATORY" if mg else "ILLUSTRATION",
                        beat_dur,
                    )
                )

        # Align slots into beat window
        t = b_start
        for j, (path, asset_id, viu, mtype, synthetic, purpose, evid, dur) in enumerate(shot_slots):
            end = min(b_end, t + dur) if j < len(shot_slots) - 1 else b_end
            if end <= t:
                end = t + 0.8
            purpose = purpose or beat.required_visual_concept
            for sr in plan.shot_requirements or []:
                if sr.beat_id == beat.beat_id:
                    purpose = sr.visual_purpose or purpose
                    evid = evid or sr.evidence_role
                    break
            edit = EditDecision(
                edit_id=f"ed:{uuid.uuid4().hex[:10]}",
                shot_id=f"shot:{beat.beat_id}:{j}",
                beat_id=beat.beat_id,
                asset_id=asset_id,
                visual_information_id=viu,
                media_type=mtype,
                source_kind=(
                    "motion_graphic"
                    if "graphic" in mtype
                    else ("generated" if synthetic else ("archive" if _is_image(path) else "stock"))
                ),
                local_path=path,
                start_time=round(t, 3),
                end_time=round(end, 3),
                duration=round(end - t, 3),
                source_in=0.0,
                fit_mode="cover",
                crop_policy="safe_center",
                motion_policy=_motion_policy_for(path, purpose, mtype, synthetic),
                transition_in="cut",
                transition_out="cut",
                transition="cut",
                visual_purpose=purpose,
                narrative_role=beat.narrative_role,
                caption_safe_area="bottom_reserved",
                evidence_role=evid,
                synthetic=synthetic,
                provenance_ref=asset_id,
                verification_ref="",
                importance=getattr(beat, "importance", None)
                or ("important" if (beat.narrative_role or "").lower() in {"hook", "reveal", "evidence"} else "supporting"),
            )
            decisions.append(edit)
            t = end
        t_cursor = b_end

    edl = EditDecisionList(
        edl_id=f"edl:{uuid.uuid4().hex[:12]}",
        job_id=job_id or plan.job_id,
        video_id=video_id or plan.video_id or plan.plan_id,
        decisions=decisions,
        total_duration_sec=round(decisions[-1].end_time, 3) if decisions else 0.0,
        narration_duration_sec=round(float(narration_duration_sec), 3),
        notes=notes,
    )
    return edl


def edl_metrics(edl: EditDecisionList) -> dict[str, Any]:
    """Benchmark counters for Stage F report."""
    decisions = edl.decisions or []
    paths = [d.local_path for d in decisions]
    unique_assets = len({d.asset_id for d in decisions if d.asset_id})
    viu_keys = set()
    for d in decisions:
        is_transform_only_still = (
            _is_image(d.local_path)
            or "still" in (d.media_type or "").lower()
            or (d.motion_policy or "").lower() in {"subtle_push", "subtle_pan"}
        )
        key = d.asset_id if is_transform_only_still else (d.visual_information_id or d.asset_id)
        if key:
            viu_keys.add(key)
    unique_vius = len(viu_keys)
    by_class = {
        "real_entity_video": 0,
        "archive_video": 0,
        "stock_video": 0,
        "motion_graphic": 0,
        "synthetic_video": 0,
        "archive_still": 0,
        "evidence_document": 0,
    }
    seconds = {k: 0.0 for k in by_class}
    for d in decisions:
        dur = float(d.duration or (d.end_time - d.start_time))
        sk = (d.source_kind or "").lower()
        mt = (d.media_type or "").lower()
        if d.synthetic and "graphic" not in mt:
            key = "synthetic_video"
        elif "graphic" in mt or sk == "motion_graphic":
            key = "motion_graphic"
        elif "document" in mt or d.evidence_role in {"EVIDENCE", "EVIDENCE_REQUIRED"}:
            key = "evidence_document" if _is_image(d.local_path) else "motion_graphic"
        elif _is_image(d.local_path) or "still" in mt:
            key = "archive_still"
        elif sk == "archive":
            key = "archive_video"
        elif sk == "stock":
            key = "stock_video"
        else:
            key = "stock_video"
        by_class[key] = by_class.get(key, 0) + 1
        seconds[key] = seconds.get(key, 0.0) + dur

    # Same-asset reuse across different beats
    asset_beats: dict[str, set[str]] = {}
    for d in decisions:
        asset_beats.setdefault(d.asset_id, set()).add(d.beat_id)
    problematic_reuse = sum(1 for a, beats in asset_beats.items() if len(beats) > 1 and a)

    return {
        "shot_count": len(decisions),
        "unique_source_assets": unique_assets,
        "unique_vius": unique_vius,
        "by_class": by_class,
        "seconds_by_class": {k: round(v, 2) for k, v in seconds.items()},
        "same_asset_multi_beat": problematic_reuse,
        "paths": paths,
    }
