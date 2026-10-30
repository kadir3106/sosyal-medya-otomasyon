"""AI Director orchestrator — visual storyboard then gated fetch (Phase 2)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.config import config
from app.director_gate import (
    AssetCandidate,
    asset_fingerprint,
    evaluate_asset,
    novelty_bonus,
    reuse_penalty,
    scene_need_from_plan,
    selection_score,
)
from app.director_planner import plan_scenes
from app.director_types import DIRECTOR_PRIORITY, ScenePlan, VisualBeat
from app.stock_media import (
    _download_file,
    _load_used_clip_ids,
    _save_used_clip_ids,
    enrich_stock_query,
    list_stock_video_candidates,
)

logger = logging.getLogger(__name__)


def plan_and_fetch_scenes(
    *,
    scene_count: int,
    topic: str,
    script_data: dict,
    output_dir: str,
    state_path: str,
    clip_duration: float,
    api_key: str | None = None,
    stats_out: dict | None = None,
) -> list[str]:
    """Storyboard (scenes → visual beats) then entity-first gated fetch."""
    script = script_data.get("script") or ""
    visual_prompts = script_data.get("visual_prompts") or []
    visual_keywords = script_data.get("visual_keywords") or []
    concrete_nouns = script_data.get("concrete_nouns") or []
    scene_stock_queries = script_data.get("scene_stock_queries")

    doc = plan_scenes(
        scene_count=scene_count,
        topic=topic,
        script=script,
        api_key=api_key if api_key is not None else config.OPENROUTER_API_KEY,
        scene_stock_queries=scene_stock_queries,
        visual_prompts=visual_prompts,
        visual_keywords=visual_keywords,
        concrete_nouns=concrete_nouns,
    )

    beats = doc.all_beats()
    # Soft cap: storytelling beats, not a fixed cut-every-N-words machine.
    max_beats = max(scene_count * 3, scene_count)
    if len(beats) > max_beats:
        beats = beats[:max_beats]
        logger.info("Director: capped visual beats to %s", max_beats)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    media_dir = Path(state_path).parent if state_path else out_dir

    # Phase 3.1 retention pre-pass: same-asset novelty before fetch (no random cuts).
    retention_events: list = []
    if bool(getattr(config, "PHASE3_RETENTION_ENABLED", True)):
        from app.phase3_retention import (
            apply_retention_to_visual_beats,
            plan_retention_events,
        )

        skeletons = []
        for beat in beats:
            sk = beat.word_to_visual_skeleton()
            sk["duration"] = beat.resolve_duration_hint(
                default=min(float(clip_duration), 2.0)
            )
            sk["primary_entities"] = list(beat.primary_entities or beat.must_show)
            skeletons.append(sk)
        retention_events = plan_retention_events(skeletons)
        apply_retention_to_visual_beats(beats, retention_events)

    ai_budget = max(int(getattr(config, "DIRECTOR_AI_IMAGE_MAX", 2)), 0)
    ai_used = 0

    clip_paths: list[str] = []
    beat_log: list[dict[str, Any]] = []
    word_to_visual: list[dict[str, Any]] = []
    fresh = 0
    cache_reuse = 0
    used_ids = _load_used_clip_ids(state_path) if state_path else set()
    newly_used: list = []
    prev_accepted: dict[str, Any] | None = None
    recent_fps: list[str] = []
    recent_blobs: list[str] = []
    person_retrieval_log: list[dict[str, Any]] = []

    for beat in beats:
        duration = beat.resolve_duration_hint(
            default=min(float(clip_duration), 2.0)
        )
        path, meta = _materialize_beat(
            beat,
            topic=topic,
            output_dir=out_dir,
            media_dir=media_dir,
            clip_duration=duration,
            clip_index=len(clip_paths),
            ai_budget_left=ai_budget - ai_used,
            visual_prompt=beat.visual_intent or beat.spoken_span,
            exclude_ids=used_ids.union(newly_used),
            prev_accepted=prev_accepted,
            recent_fps=recent_fps,
            recent_blobs=recent_blobs,
            person_log=person_retrieval_log,
        )
        chain = {
            **beat.word_to_visual_skeleton(),
            "duration": duration,
            "rejected_candidates": [
                a
                for a in (meta.get("attempts") or [])
                if a.get("rejection_reason")
            ],
            "candidates_considered": len(meta.get("attempts") or []),
            "selected_asset": None,
            "relevance_score": meta.get("score"),
            "entity_score": meta.get("entity_score"),
            "specificity_score": meta.get("specificity_score"),
            "gate_reason": meta.get("gate_reason"),
            "visual_change_applied": meta.get("visual_change_applied"),
            "media_kind": meta.get("kind"),
            "kind": meta.get("kind"),
            "path": path,
            "asset_id": meta.get("asset_id"),
        }
        if path:
            from app.storyboard import compute_visual_information_id, enrich_beat_dict

            chain["selected_asset"] = {
                "path": path,
                "kind": meta.get("kind"),
                "provider": meta.get("provider") or meta.get("source"),
                "asset_id": meta.get("asset_id"),
                "metadata": meta.get("metadata"),
            }
            # Asset-bound visual information id (crop/zoom share this)
            chain["visual_information_id"] = compute_visual_information_id(
                asset_id=str(meta.get("asset_id") or "") or None,
                entity=(beat.primary_entities[0] if beat.primary_entities else ""),
                concept=beat.concept,
                evidence_role=beat.evidence_role,
                required_visual_concept=beat.required_visual_concept,
                media_kind=str(meta.get("kind") or ""),
            )
            chain = enrich_beat_dict(chain)
            prev_accepted = {
                "path": path,
                "kind": meta.get("kind"),
                "provider": meta.get("provider") or meta.get("source"),
                "asset_id": meta.get("asset_id"),
                "entities": list(beat.primary_entities or beat.must_show),
                "still_path": meta.get("still_path"),
            }
            fp = asset_fingerprint(
                provider=str(prev_accepted.get("provider") or ""),
                asset_id=str(prev_accepted.get("asset_id") or "") or None,
                url=str((meta.get("metadata") or {}).get("url") or ""),
            )
            if fp:
                recent_fps.append(fp)
            blob = " ".join(
                str((meta.get("metadata") or {}).get(k) or "")
                for k in ("title", "tags", "alt", "description")
            )
            if blob.strip():
                recent_blobs.append(blob)
            clip_paths.append(path)
            if meta.get("kind") == "ai_image":
                ai_used += 1
            # Only true used_clips.json hits count as stock-cache pollution.
            # Intentional punch-in / crop reframe is not cache drift.
            if meta.get("cache_reuse"):
                cache_reuse += 1
            else:
                fresh += 1
            aid = meta.get("asset_id")
            if aid is not None and meta.get("provider") and not meta.get(
                "visual_change_applied"
            ):
                from app.stock_media import _clip_id

                newly_used.append(_clip_id(str(meta["provider"]), aid))
        word_to_visual.append(chain)
        beat_log.append(
            {
                "beat": beat.index,
                "scene": beat.scene_index,
                "word_to_visual": chain,
                **meta,
            }
        )

    if state_path and newly_used:
        _save_used_clip_ids(state_path, used_ids.union(newly_used))

    if stats_out is not None:
        from app.no_slideshow_gate import (
            evaluate_no_slideshow,
            visual_information_units_from_shots,
        )
        from app.beat_recovery import (
            build_all_beat_coverage,
            recover_uncovered_beat,
        )
        from app.story_domains import (
            analyze_source_assets,
            build_beat_research_requirement,
        )
        from app.storyboard import analyze_storyboard_coverage, storyboard_before_retrieval

        # Decision-first storyboard snapshot (from final script text)
        pre_board = [
            s.to_dict()
            for s in storyboard_before_retrieval(script or topic or "", topic=topic)
        ]
        # Beat coverage recovery ladder (never silent unrelated prior-asset fill)
        coverage_rows = build_all_beat_coverage(word_to_visual, topic=topic)
        verified_facts = []
        if isinstance(script_data, dict):
            sq = script_data.get("script_quality") or {}
            verified_facts = list(sq.get("replacement_research") or [])
        recovery_log: list[dict] = []
        used_queries_global: set[str] = set()
        for cov in coverage_rows:
            if cov.importance != "important" or cov.status != "UNCOVERED":
                continue
            if len(recovery_log) >= 4:
                break
            idx = int(cov.beat_id) if str(cov.beat_id).isdigit() else -1
            if idx < 0 or idx >= len(beats):
                # resolve by matching index in word_to_visual
                try:
                    idx = next(
                        i
                        for i, b in enumerate(word_to_visual)
                        if str(b.get("beat") if b.get("beat") is not None else i)
                        == str(cov.beat_id)
                    )
                except StopIteration:
                    continue
            beat = beats[idx]
            beat.visual_change = "new_asset"
            duration = beat.resolve_duration_hint(
                default=min(float(clip_duration), 2.0)
            )

            def _mat(b, **kwargs):
                return _materialize_beat(b, **kwargs)

            path, meta, cov_out = recover_uncovered_beat(
                beat,
                topic=topic,
                coverage=cov,
                materialize_fn=_mat,
                output_dir=out_dir,
                media_dir=media_dir,
                clip_index=idx,
                clip_duration=duration,
                ai_budget_left=max(0, ai_budget - ai_used),
                exclude_ids=used_ids.union(newly_used),
                recent_fps=recent_fps,
                recent_blobs=recent_blobs,
                person_log=person_retrieval_log,
                verified_facts=verified_facts,
                used_queries=used_queries_global,
            )
            for a in cov_out.attempts:
                if a.get("query"):
                    used_queries_global.add(str(a["query"]).lower())
            recovery_log.append(
                {
                    "beat_id": cov_out.beat_id,
                    "importance": cov_out.importance,
                    "status": cov_out.status,
                    "failure_reason": cov_out.failure_reason,
                    "attempts": cov_out.attempts,
                    "providers_tried": cov_out.providers_tried,
                    "motion_graphic_attempted": cov_out.motion_graphic_attempted,
                    "evidence_visual_used": cov_out.evidence_visual_used,
                    "accepted": bool(path),
                }
            )
            for ci, c in enumerate(coverage_rows):
                if str(c.beat_id) == str(cov.beat_id):
                    coverage_rows[ci] = cov_out
                    break
            if path:
                from app.storyboard import compute_visual_information_id, enrich_beat_dict

                chain = {
                    **beat.word_to_visual_skeleton(),
                    "duration": duration,
                    "rejected_candidates": [
                        a
                        for a in (meta.get("attempts") or [])
                        if a.get("rejection_reason")
                    ],
                    "candidates_considered": len(meta.get("attempts") or []),
                    "selected_asset": {
                        "path": path,
                        "kind": meta.get("kind"),
                        "provider": meta.get("provider") or meta.get("source"),
                        "asset_id": meta.get("asset_id"),
                        "metadata": meta.get("metadata"),
                    },
                    "relevance_score": meta.get("score"),
                    "entity_score": meta.get("entity_score"),
                    "specificity_score": meta.get("specificity_score"),
                    "gate_reason": meta.get("gate_reason"),
                    "visual_change_applied": meta.get("visual_change_applied")
                    or "new_asset",
                    "media_kind": meta.get("kind"),
                    "kind": meta.get("kind"),
                    "path": path,
                    "asset_id": meta.get("asset_id"),
                    "coverage_recovery": True,
                    "recovery_attempts": cov_out.attempts,
                    "beat_coverage": cov_out.to_dict(),
                }
                chain["visual_information_id"] = compute_visual_information_id(
                    asset_id=str(meta.get("asset_id") or "") or None,
                    entity=(beat.primary_entities[0] if beat.primary_entities else ""),
                    concept=beat.concept,
                    evidence_role=beat.evidence_role,
                    required_visual_concept=beat.required_visual_concept,
                    media_kind=str(meta.get("kind") or ""),
                )
                cov_out.selected_visual_information_id = chain["visual_information_id"]
                chain = enrich_beat_dict(chain)
                word_to_visual[idx] = chain
                aid = meta.get("asset_id")
                if aid is not None and meta.get("provider") and meta.get("provider") not in {
                    "motion_graphic",
                    "ai_image",
                }:
                    from app.stock_media import _clip_id

                    newly_used.append(_clip_id(str(meta["provider"]), aid))
                if meta.get("kind") in {"ai_image", "motion_graphic"}:
                    ai_used += 1
                fp = asset_fingerprint(
                    provider=str(meta.get("provider") or ""),
                    asset_id=str(meta.get("asset_id") or "") or None,
                )
                if fp:
                    recent_fps.append(fp)

        # Rebuild clip list from word_to_visual (beat-aligned; no silent filler pads)
        clip_paths = []
        for b in word_to_visual:
            p = b.get("path") or (b.get("selected_asset") or {}).get("path")
            if p:
                clip_paths.append(str(p))

        # Rebuild coverage after recovery
        coverage_rows = build_all_beat_coverage(word_to_visual, topic=topic)
        # Merge attempt diagnostics from recovery_log into rows
        by_id = {str(r["beat_id"]): r for r in recovery_log}
        for i, row in enumerate(coverage_rows):
            extra = by_id.get(str(row.beat_id))
            if extra:
                row.attempts = extra.get("attempts") or row.attempts
                row.providers_tried = extra.get("providers_tried") or row.providers_tried
                row.motion_graphic_attempted = bool(
                    extra.get("motion_graphic_attempted")
                )
                row.evidence_visual_used = bool(extra.get("evidence_visual_used"))
                if row.status == "UNCOVERED" and extra.get("failure_reason"):
                    row.failure_reason = str(extra["failure_reason"])
                coverage_rows[i] = row

        coverage = analyze_storyboard_coverage(word_to_visual)
        source_stats = analyze_source_assets(word_to_visual)
        beat_reqs = [
            r.to_dict()
            for i, b in enumerate(word_to_visual)
            if (r := build_beat_research_requirement(b, index=i, topic=topic))
        ]
        sc = (stats_out or {}).get("story_consistency") or {}
        gate = evaluate_no_slideshow(
            word_to_visual,
            retention_events=[
                e.to_dict() if hasattr(e, "to_dict") else e for e in retention_events
            ],
            topic=topic,
            story_consistency=sc,
            beat_coverage=[c.to_dict() for c in coverage_rows],
            recovery_log=recovery_log,
        )
        vius = visual_information_units_from_shots(word_to_visual)
        total = len(clip_paths)
        stats_out.update(
            {
                "engine": "director",
                "director_plan": doc.to_meta(),
                "hook_director": (doc.hook.to_meta() if doc.hook else None),
                "visual_beats": [b.to_meta() for b in beats],
                "word_to_visual": word_to_visual,
                "scene_relevance": beat_log,
                "fresh_downloads": fresh,
                "cache_reuse_downloads": cache_reuse,
                "stock_cache_reuse_ratio": (
                    round(cache_reuse / total, 3) if total else 0.0
                ),
                "ai_image_used": ai_used,
                "beat_count": len(beats),
                "clip_count": total,
                "priority": list(DIRECTOR_PRIORITY),
                "retention_events": [
                    e.to_dict() if hasattr(e, "to_dict") else e
                    for e in retention_events
                ],
                "person_retrieval": person_retrieval_log,
                "storyboard_before_retrieval": pre_board,
                "storyboard_coverage": coverage.to_dict(),
                "visual_information_units": vius,
                "no_slideshow_gate": gate.to_dict(),
                "source_asset_stats": source_stats,
                "important_beat_coverage": [c.to_dict() for c in coverage_rows],
                "beat_coverage": [c.to_dict() for c in coverage_rows],
                "beat_research_requirements": beat_reqs,
                "important_beat_retry": recovery_log,
                "beat_recovery": recovery_log,
                "shot_count": source_stats.get("shot_count"),
                "unique_source_asset_count": source_stats.get(
                    "unique_source_asset_count"
                ),
            }
        )

    # Phase 1: never fill with ungated unrelated stock (pacing must not override relevance).
    target = max(scene_count, 1)
    if len(clip_paths) < target:
        missing = target - len(clip_paths)
        logger.warning(
            "Director: %s clips missing after gated beat fetch — no ungated stock fill",
            missing,
        )
        if stats_out is not None:
            stats_out["ungated_fill"] = False
            stats_out["missing_scenes"] = missing
        for beat in beats[len(clip_paths) :]:
            if ai_used >= ai_budget and not beat.allow_ai_generation:
                break
            if not beat.allow_ai_generation and ai_budget - ai_used <= 0:
                continue
            duration = beat.resolve_duration_hint(default=min(float(clip_duration), 2.0))
            path, meta = _try_ai_image(
                beat,
                output_dir=out_dir,
                clip_index=len(clip_paths),
                clip_duration=duration,
                visual_prompt=beat.visual_intent,
                reason="controlled_ai_after_stock_miss",
            )
            if path:
                clip_paths.append(path)
                ai_used += 1
                chain = {
                    **beat.word_to_visual_skeleton(),
                    "duration": duration,
                    "selected_asset": {
                        "path": path,
                        "kind": "ai_image",
                        "provider": "ai_image",
                    },
                    "rejected_candidates": [],
                    "gate_reason": meta.get("gate_reason"),
                    "visual_change_applied": None,
                }
                word_to_visual.append(chain)
                beat_log.append(
                    {"beat": beat.index, "scene": beat.scene_index, "word_to_visual": chain, **meta}
                )
        if stats_out is not None:
            stats_out["scene_relevance"] = beat_log
            stats_out["word_to_visual"] = word_to_visual
            stats_out["ai_image_used"] = ai_used

    return clip_paths


def _materialize_beat(
    beat: VisualBeat,
    *,
    topic: str,
    output_dir: Path,
    clip_duration: float,
    clip_index: int,
    ai_budget_left: int,
    visual_prompt: str,
    exclude_ids: set,
    prev_accepted: dict[str, Any] | None = None,
    recent_fps: list[str] | None = None,
    recent_blobs: list[str] | None = None,
    media_dir: Path | None = None,
    person_log: list | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Entity-first retrieval ladder + Phase 1 quality gate on every candidate.

    Visual change may reuse the previous accepted asset (punch-in / crop) when
    the beat asks for it — new download is not required for every attention beat.
    """
    attempts: list[dict[str, Any]] = []
    recent_fps = list(recent_fps or [])
    recent_blobs = list(recent_blobs or [])
    last_meta: dict[str, Any] = {
        "kind": None,
        "source": "miss",
        "query": None,
        "score": 0.0,
        "entity_score": 0.0,
        "specificity_score": 0.0,
        "intent": beat.visual_intent[:120],
        "narrative_role": beat.narrative_role,
        "primary_entities": beat.primary_entities,
        "shot_type": beat.shot_type,
        "attempts": attempts,
    }

    # Same good asset + new framing — only when entity continuity AND not an
    # exact short-window duplicate without a named-entity requirement change.
    # Important distinct beats must run their own retrieval ladder.
    important_roles = {
        "hook",
        "entity_proof",
        "document",
        "money",
        "place",
        "cta",
    }
    important_evidence = {"archive", "proof", "document", "location", "contrast"}
    force_fresh = (
        beat.narrative_role in important_roles
        or beat.evidence_role in important_evidence
    )
    if (
        beat.wants_reuse_visual_change()
        and prev_accepted
        and prev_accepted.get("path")
        and not force_fresh
    ):
        prev_ents = {e.lower() for e in (prev_accepted.get("entities") or [])}
        cur_ents = {e.lower() for e in (beat.primary_entities or beat.must_show)}
        prev_fp = asset_fingerprint(
            provider=str(prev_accepted.get("provider") or ""),
            asset_id=str(prev_accepted.get("asset_id") or "") or None,
        )
        exact_recent = bool(prev_fp) and reuse_penalty(prev_fp, recent_fps) >= 0.55
        # New named entity on this beat → do not stretch prior B-roll.
        entity_shift = bool(cur_ents) and bool(prev_ents) and not (prev_ents & cur_ents)
        if (
            not entity_shift
            and not exact_recent
            and (not cur_ents or (prev_ents & cur_ents) or not prev_ents)
        ):
            reused = _apply_visual_change_reuse(
                prev_accepted,
                output_dir=output_dir,
                clip_index=clip_index,
                clip_duration=clip_duration,
                change=beat.visual_change,
                motion=beat.motion,
            )
            if reused:
                path, reuse_meta = reused
                last_meta.update(reuse_meta)
                last_meta["accepted"] = True
                last_meta["visual_change_applied"] = beat.visual_change
                last_meta["beat"] = beat.to_meta()
                last_meta["attempts"] = attempts
                return path, last_meta
    elif force_fresh and beat.wants_reuse_visual_change():
        # Override retention-forced reuse — retrieve a new source asset
        beat.visual_change = "new_asset"

    raw_queries = beat.entity_first_queries(topic=topic)
    queries = []
    for q in raw_queries:
        # Keep person/archive queries clean — full-topic enrich hurts specificity.
        if any(
            cue in q.lower()
            for cue in ("portrait", "archive", "founder", "historical")
        ):
            queries.append(q[:100])
        else:
            queries.append(enrich_stock_query(q, topic=topic))
    queries = queries or [enrich_stock_query(topic, topic=topic)]
    # Cap query fan-out — long ladders + Pexels 429 = multi-hour hangs
    queries = queries[:3]
    kinds = beat.kind_chain()
    # Ownership / evidence beats: still/archive first; skip video spam under rate limits
    if beat.evidence_role in {"proof", "document", "archive"} or beat.concept in {
        "ownership",
        "foundation",
    }:
        kinds = [k for k in kinds if k != "stock_video"]
        if "stock_photo" not in kinds:
            kinds = ["stock_photo"] + kinds
        if not kinds:
            kinds = ["stock_photo", "ai_image"]
    last_meta["query"] = queries[0]

    need = scene_need_from_plan(
        queries=queries,
        must_show=beat.must_show,
        avoid=beat.avoid,
        required_entities=beat.primary_entities or beat.must_show,
        scene_type=beat.narrative_role,
        visual_intent=beat.visual_intent or beat.spoken_span,
        narrative_role=beat.narrative_role,
    )
    if not need.must_show and not need.required_entities:
        from app.stock_media import extract_proper_phrases

        extracted = extract_proper_phrases(
            f"{topic}. {beat.visual_intent}. {beat.spoken_span}. {' '.join(queries)}"
        )[:4]
        if extracted:
            need.must_show = extracted
            need.required_entities = extracted
            need.entity_specific = True

    # Phase 3.1: person archive BEFORE generic stock (portrait ≫ storefront).
    from app.person_archive import looks_like_person_name, try_cached_or_fetch_person_image

    person_ents = [
        e
        for e in (beat.primary_entities or beat.must_show or [])
        if looks_like_person_name(e)
    ]
    cache_root = media_dir or output_dir
    for pe in person_ents[:1]:
        # Person portrait need must NOT require co-mentioned orgs (Foundation),
        # or the correct portrait fails missing_required_entities / below_threshold.
        person_need = scene_need_from_plan(
            queries=[f"{pe} portrait archive", pe],
            must_show=[pe],
            required_entities=[pe],
            avoid=list(beat.avoid or []),
            scene_type="entity_proof",
            visual_intent=f"Archive / real-world portrait of {pe}",
            narrative_role="entity_proof",
        )
        cand, pmeta, gate = try_cached_or_fetch_person_image(
            pe, media_dir=cache_root, need=person_need, attempts=attempts
        )
        from_cache = bool(
            pmeta and pmeta.get("validated") and pmeta.get("entity_key")
        )
        entry = {
            "entity": pe,
            "attempted": True,
            "accepted": False,
            "provider": (pmeta or {}).get("provider"),
            "asset_id": (pmeta or {}).get("asset_id"),
            "page_title": (pmeta or {}).get("title"),
            "rejection_reason": None
            if (gate and getattr(gate, "accepted", False))
            else (getattr(gate, "reason", None) if gate else "no_candidate"),
            "source": "person_cache" if from_cache else "wikipedia",
        }
        if person_log is not None:
            person_log.append(entry)
        if cand and gate and gate.accepted and cand.download_url:
            path, meta = _download_person_archive_clip(
                cand,
                pmeta or {},
                gate,
                output_dir=output_dir,
                clip_index=clip_index,
                clip_duration=clip_duration,
                motion=beat.motion,
            )
            if path:
                entry["accepted"] = True
                entry["rejection_reason"] = None
                entry["clip_path"] = path
                last_meta = {
                    **last_meta,
                    **meta,
                    "kind": "stock_photo",
                    "query": pe,
                    "attempts": attempts,
                    "beat": beat.to_meta(),
                    "person_archive": True,
                    "accepted": True,
                }
                return path, last_meta
            entry["accepted"] = False
            entry["rejection_reason"] = (meta or {}).get("gate_reason") or "person_clip_failed"

    for kind in kinds:
        if kind == "ai_image" and (
            not beat.allow_ai_generation or ai_budget_left <= 0
        ):
            continue
        for query in queries:
            if kind == "stock_video":
                path, meta = _try_stock_video_gated(
                    query=query,
                    need=need,
                    output_dir=output_dir,
                    clip_index=clip_index,
                    exclude_ids=exclude_ids,
                    attempts=attempts,
                    recent_fps=recent_fps,
                    recent_blobs=recent_blobs,
                )
            elif kind == "stock_photo":
                path, meta = _try_stock_photo_gated(
                    query=query,
                    need=need,
                    output_dir=output_dir,
                    clip_index=clip_index,
                    clip_duration=clip_duration,
                    attempts=attempts,
                    motion=_motion_to_kenburns(beat.motion),
                    recent_fps=recent_fps,
                    recent_blobs=recent_blobs,
                )
            elif kind == "ai_image":
                path, meta = _try_ai_image(
                    beat,
                    output_dir=output_dir,
                    clip_index=clip_index,
                    clip_duration=clip_duration,
                    visual_prompt=visual_prompt,
                    reason="kind_ladder_ai_image",
                )
                attempts.append({**meta, "query": query, "kind": kind})
            else:
                continue

            last_meta = {
                **last_meta,
                **meta,
                "kind": kind,
                "query": query,
                "attempts": attempts,
                "beat": beat.to_meta(),
            }
            if path:
                last_meta["accepted"] = True
                return path, last_meta

    last_meta["fallback_reason"] = "no_gated_asset"
    return None, last_meta


def _download_person_archive_clip(
    cand: AssetCandidate,
    pmeta: dict[str, Any],
    gate: Any,
    *,
    output_dir: Path,
    clip_index: int,
    clip_duration: float,
    motion: str = "slow_push",
) -> tuple[str | None, dict[str, Any]]:
    """Download gated Wikipedia/Commons portrait → Ken Burns clip."""
    from app.ai_visuals import image_to_motion_clip
    from app.http_client import session

    img = output_dir / f"person_archive_{clip_index}.jpg"
    dest = output_dir / f"clip_{clip_index}.mp4"
    url = str(cand.download_url or "").split("?")[0]  # drop utm tracking
    try:
        resp = session.get(
            url or cand.download_url,
            timeout=25,
            headers={
                "User-Agent": "sosyal-medya-otomasyon/phase31 (person-archive; contact=local)",
                "Accept": "image/*,*/*",
                "Referer": "https://en.wikipedia.org/",
            },
        )
        if resp.status_code != 200:
            return None, {
                "source": "miss",
                "gate_reason": f"person_download_http_{resp.status_code}",
            }
        data = resp.content
        if len(data) <= 1024 or b"<html" in data[:200].lower():
            return None, {"source": "miss", "gate_reason": "person_download_too_small"}
        img.write_bytes(data)
        digest = hashlib.sha1(data).hexdigest()[:16]
        kb = _motion_to_kenburns(motion)
        if kb not in {"zoom_in", "zoom_out", "punch_in"}:
            kb = "zoom_in"
        image_to_motion_clip(img, dest, duration=clip_duration, motion_type=kb)
    except Exception as exc:
        logger.warning("person archive clip failed: %s", exc)
        return None, {"source": "miss", "gate_reason": f"person_clip_error:{exc}"}
    if not dest.is_file():
        return None, {"source": "miss", "gate_reason": "person_clip_missing"}
    return str(dest), {
        "kind": "stock_photo",
        "source": cand.provider,
        "provider": cand.provider,
        "asset_id": cand.asset_id,
        "score": getattr(gate, "relevance_score", 0.9),
        "entity_score": getattr(gate, "entity_score", 0.9),
        "specificity_score": getattr(gate, "specificity_score", 0.85),
        "gate_reason": "person_archive_accepted",
        "still_path": str(img),
        "metadata": {
            "title": cand.title,
            "url": cand.url,
            "tags": cand.tags,
            "description": cand.description,
            "attribution": pmeta.get("attribution"),
            "page_url": pmeta.get("page_url"),
            "content_hash": digest,
        },
    }


def _motion_to_kenburns(motion: str) -> str:
    m = (motion or "").strip().lower()
    if m in {"punch_in", "crop_zoom"}:
        return "punch_in"
    if m in {"static_kb", "hold"}:
        return "zoom_out"
    return "zoom_in"


def _apply_visual_change_reuse(
    prev: dict[str, Any],
    *,
    output_dir: Path,
    clip_index: int,
    clip_duration: float,
    change: str,
    motion: str,
) -> tuple[str, dict[str, Any]] | None:
    """Re-frame previous accepted asset — counts as visual change without new stock."""
    import subprocess

    src = Path(str(prev.get("path") or ""))
    if not src.is_file():
        return None
    dest = output_dir / f"clip_{clip_index}.mp4"
    still = prev.get("still_path")
    still_path = Path(str(still)) if still else None
    kb = _motion_to_kenburns(motion or change)
    try:
        if still_path and still_path.is_file():
            from app.ai_visuals import image_to_motion_clip

            image_to_motion_clip(
                still_path, dest, duration=clip_duration, motion_type=kb
            )
        else:
            # Punch-in / crop from prior clip (no new download).
            frames = max(int(clip_duration * 25), 1)
            if kb == "punch_in":
                z = "min(zoom+0.0016,1.28)"
            elif kb == "zoom_out":
                z = "if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0009))"
            else:
                z = "min(zoom+0.0009,1.18)"
            vf = (
                f"scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,"
                f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s=1080x1920:fps=25"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-vf",
                    vf,
                    "-t",
                    str(clip_duration),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-preset",
                    "veryfast",
                    str(dest),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as exc:
        logger.warning("visual_change reuse failed (%s): %s", change, exc)
        return None
    if not dest.is_file():
        return None
    return str(dest), {
        "kind": prev.get("kind") or "stock_video",
        "source": prev.get("provider") or "reuse",
        "provider": prev.get("provider"),
        "asset_id": prev.get("asset_id"),
        "score": 0.85,
        "entity_score": 0.85,
        "gate_reason": f"visual_change:{change}",
        "cache_reuse": True,
        "still_path": str(still_path) if still_path else None,
    }


def _materialize_scene(
    scene: ScenePlan,
    *,
    topic: str,
    output_dir: Path,
    clip_duration: float,
    clip_index: int,
    ai_budget_left: int,
    visual_prompt: str,
    exclude_ids: set,
) -> tuple[str | None, dict[str, Any]]:
    """Legacy single-scene path — delegates to first/only beat."""
    beat = scene.ensure_beats()[0]
    if visual_prompt and not beat.visual_intent:
        beat.visual_intent = visual_prompt
    return _materialize_beat(
        beat,
        topic=topic,
        output_dir=output_dir,
        clip_duration=clip_duration,
        clip_index=clip_index,
        ai_budget_left=ai_budget_left,
        visual_prompt=visual_prompt or beat.visual_intent,
        exclude_ids=exclude_ids,
    )


def _try_stock_video_gated(
    *,
    query: str,
    need,
    output_dir: Path,
    clip_index: int,
    exclude_ids: set,
    attempts: list,
    recent_fps: list[str] | None = None,
    recent_blobs: list[str] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    candidates = list_stock_video_candidates(
        query,
        api_key=config.PEXELS_API_KEY,
        pixabay_api_key=getattr(config, "PIXABAY_API_KEY", ""),
        enable_mixkit=getattr(config, "ENABLE_MIXKIT_STOCK", True),
        exclude_ids=exclude_ids,
        max_candidates=8,
    )
    recent_fps = list(recent_fps or [])
    recent_blobs = list(recent_blobs or [])
    ranked: list[tuple[float, Any, Any, dict]] = []
    for hit in candidates:
        meta = hit.get("metadata") or {}
        cand = AssetCandidate(
            provider=str(hit.get("provider") or "stock"),
            asset_id=str(hit["asset_id"]) if hit.get("asset_id") is not None else None,
            download_url=hit.get("download_url"),
            title=str(meta.get("title") or ""),
            tags=str(meta.get("tags") or ""),
            description=str(meta.get("description") or ""),
            url=str(meta.get("url") or meta.get("page_url") or ""),
            user=str(meta.get("user") or ""),
            kind="stock_video",
        )
        gate = evaluate_asset(cand, need)
        fp = asset_fingerprint(
            provider=cand.provider,
            asset_id=cand.asset_id,
            url=cand.url,
            download_url=cand.download_url,
        )
        pen = reuse_penalty(fp, recent_fps)
        nov = novelty_bonus(cand.metadata_blob(), recent_blobs)
        # Source novelty: new fingerprint beats reused when relevance is similar
        sn = 0.12 if fp and reuse_penalty(fp, recent_fps) < 0.15 else 0.0
        score = selection_score(gate, reuse_pen=pen, novelty=nov, source_novelty=sn)
        attempt = {
            "kind": "stock_video",
            "query": query,
            "provider": cand.provider,
            "asset_id": cand.asset_id,
            "metadata_excerpt": cand.metadata_blob()[:180],
            "relevance_score": gate.relevance_score,
            "entity_score": gate.entity_score,
            "specificity_score": gate.specificity_score,
            "selection_score": score,
            "reuse_penalty": pen,
            "source_novelty": sn,
            "rejection_reason": None if gate.accepted else gate.reason,
            "forbidden_hit": gate.forbidden_hit,
        }
        attempts.append(attempt)
        logger.info(
            "[director-gate] query=%r provider=%s accept=%s reason=%s "
            "rel=%.3f ent=%.3f spec=%.3f sel=%.3f",
            query,
            cand.provider,
            gate.accepted,
            gate.reason,
            gate.relevance_score,
            gate.entity_score,
            gate.specificity_score,
            score,
        )
        if gate.accepted and cand.download_url:
            ranked.append((score, cand, gate, hit))

    if not ranked:
        return None, {
            "source": "miss",
            "score": 0.0,
            "entity_score": 0.0,
            "specificity_score": 0.0,
            "gate_reason": "all_candidates_rejected",
        }

    ranked.sort(key=lambda row: row[0], reverse=True)
    score, cand, gate, hit = ranked[0]
    # Exact recent duplicate: only keep if no better alternative exists.
    fp = asset_fingerprint(
        provider=cand.provider, asset_id=cand.asset_id, url=cand.url
    )
    if reuse_penalty(fp, recent_fps) >= 0.9 and len(ranked) > 1:
        score, cand, gate, hit = ranked[1]

    clip_path = output_dir / f"clip_{clip_index}.mp4"
    _download_file(cand.download_url, clip_path)
    return str(clip_path), {
        "source": cand.provider,
        "provider": cand.provider,
        "asset_id": cand.asset_id,
        "score": gate.relevance_score,
        "entity_score": gate.entity_score,
        "specificity_score": gate.specificity_score,
        "selection_score": score,
        "gate_reason": gate.reason,
        "cache_reuse": bool(hit.get("reused")),
        "metadata": {
            "title": cand.title,
            "tags": cand.tags,
            "url": cand.url,
            "user": cand.user,
        },
    }


def _try_stock_photo_gated(
    *,
    query: str,
    need,
    output_dir: Path,
    clip_index: int,
    clip_duration: float,
    attempts: list,
    motion: str = "zoom_in",
    recent_fps: list[str] | None = None,
    recent_blobs: list[str] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    from app.ai_visuals import image_to_motion_clip
    from app.http_client import session

    api_key = config.PEXELS_API_KEY
    if not api_key:
        return None, {"source": "miss", "score": 0.0, "gate_reason": "no_pexels_key"}

    try:
        resp = session.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "orientation": "portrait", "per_page": 8},
            timeout=15,
        )
        if resp.status_code != 200:
            return None, {
                "source": "miss",
                "score": 0.0,
                "gate_reason": f"pexels_http_{resp.status_code}",
            }
        photos = resp.json().get("photos") or []
    except Exception as exc:
        logger.warning("director photo search failed: %s", exc)
        return None, {"source": "miss", "score": 0.0, "gate_reason": "photo_search_error"}

    recent_fps = list(recent_fps or [])
    recent_blobs = list(recent_blobs or [])
    ranked: list[tuple[float, Any, Any, dict]] = []
    for photo in photos:
        meta = {
            "url": str(photo.get("url") or ""),
            "photographer": str(photo.get("photographer") or ""),
            "alt": str(photo.get("alt") or ""),
            "title": str(photo.get("alt") or ""),
            "tags": str(photo.get("alt") or ""),
            "description": str(photo.get("alt") or ""),
            "user": str(photo.get("photographer") or ""),
        }
        cand = AssetCandidate(
            provider="pexels_photo",
            asset_id=str(photo.get("id")) if photo.get("id") is not None else None,
            download_url=(
                (photo.get("src") or {}).get("large2x")
                or (photo.get("src") or {}).get("original")
                or (photo.get("src") or {}).get("large")
            ),
            title=meta["title"],
            tags=meta["tags"],
            description=meta["description"],
            url=meta["url"],
            user=meta["user"],
            kind="stock_photo",
        )
        gate = evaluate_asset(cand, need)
        fp = asset_fingerprint(
            provider=cand.provider,
            asset_id=cand.asset_id,
            url=cand.url,
            download_url=cand.download_url,
        )
        pen = reuse_penalty(fp, recent_fps)
        nov = novelty_bonus(cand.metadata_blob(), recent_blobs)
        sn = 0.12 if fp and reuse_penalty(fp, recent_fps) < 0.15 else 0.0
        score = selection_score(gate, reuse_pen=pen, novelty=nov, source_novelty=sn)
        attempts.append(
            {
                "kind": "stock_photo",
                "query": query,
                "provider": "pexels_photo",
                "asset_id": cand.asset_id,
                "metadata_excerpt": cand.metadata_blob()[:180],
                "relevance_score": gate.relevance_score,
                "entity_score": gate.entity_score,
                "specificity_score": gate.specificity_score,
                "selection_score": score,
                "reuse_penalty": pen,
                "source_novelty": sn,
                "rejection_reason": None if gate.accepted else gate.reason,
                "forbidden_hit": gate.forbidden_hit,
            }
        )
        if gate.accepted and cand.download_url:
            ranked.append((score, cand, gate, meta))

    if not ranked:
        return None, {
            "source": "miss",
            "score": 0.0,
            "gate_reason": "all_photo_candidates_rejected",
        }

    ranked.sort(key=lambda row: row[0], reverse=True)
    score, cand, gate, meta = ranked[0]
    fp = asset_fingerprint(
        provider=cand.provider, asset_id=cand.asset_id, url=cand.url
    )
    if reuse_penalty(fp, recent_fps) >= 0.9 and len(ranked) > 1:
        score, cand, gate, meta = ranked[1]

    img = output_dir / f"director_photo_{clip_index}.jpg"
    try:
        img_data = session.get(cand.download_url, timeout=20).content
        if len(img_data) <= 1024:
            return None, {
                "source": "miss",
                "score": 0.0,
                "gate_reason": "photo_download_too_small",
            }
        img.write_bytes(img_data)
    except Exception:
        return None, {
            "source": "miss",
            "score": 0.0,
            "gate_reason": "photo_download_failed",
        }
    clip_path = output_dir / f"clip_{clip_index}.mp4"
    image_to_motion_clip(
        img, clip_path, duration=clip_duration, motion_type=motion
    )
    return str(clip_path), {
        "source": "pexels_photo",
        "provider": "pexels_photo",
        "asset_id": cand.asset_id,
        "score": gate.relevance_score,
        "entity_score": gate.entity_score,
        "specificity_score": gate.specificity_score,
        "selection_score": score,
        "gate_reason": gate.reason,
        "metadata": meta,
        "still_path": str(img),
    }


def _try_ai_image(
    plan_obj: ScenePlan | VisualBeat,
    *,
    output_dir: Path,
    clip_index: int,
    clip_duration: float,
    visual_prompt: str,
    reason: str,
) -> tuple[str | None, dict[str, Any]]:
    from app.ai_visuals import generate_ai_image, image_to_motion_clip
    from app.errors import FalAuthBillingError

    img = output_dir / f"director_ai_{clip_index}.jpg"
    clip_path = output_dir / f"clip_{clip_index}.mp4"
    intent = getattr(plan_obj, "visual_intent", "") or ""
    must = getattr(plan_obj, "must_show", None) or []
    prompt = (visual_prompt or intent or "").strip()
    ents = " ".join(must)
    if ents and ents.lower() not in prompt.lower():
        prompt = f"{ents}, {prompt}".strip(", ")
    try:
        generate_ai_image(prompt, img, prefer_fal=True)
    except FalAuthBillingError:
        raise
    except Exception as exc:
        logger.warning("director ai_image failed: %s", exc)
        return None, {
            "kind": "ai_image",
            "source": "ai_image",
            "score": 0.0,
            "fallback_reason": reason,
            "rejection_reason": str(exc),
        }
    if not img.is_file():
        return None, {
            "kind": "ai_image",
            "source": "ai_image",
            "score": 0.0,
            "fallback_reason": reason,
            "rejection_reason": "no_file",
        }
    image_to_motion_clip(img, clip_path, duration=clip_duration, motion_type="zoom_in")
    return str(clip_path), {
        "kind": "ai_image",
        "source": "ai_image",
        "provider": "ai_image",
        "score": 0.5,
        "entity_score": 0.0,
        "gate_reason": "controlled_ai",
        "fallback_reason": reason,
        "accepted": True,
    }
