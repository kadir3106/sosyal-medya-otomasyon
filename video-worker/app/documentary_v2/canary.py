"""Explicit, unpublished Stage G canary packaging and scoring."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from app.documentary_v2.assembly.orchestrator import StageFResult
from app.documentary_v2.pipeline_mode import resolve_pipeline_mode
from app.documentary_v2.review_runner import MANDATORY_GATES, run_topic_review
from app.documentary_v2.schemas import PipelineMode


STORY_TYPES = {
    "named_company_ownership",
    "historical_founder_person",
    "physical_process",
    "historical_location",
    "abstract_financial_mechanism",
}
FAILURE_CODES = {
    "ENTITY_SELECTION": "WRONG_ENTITY ENTITY_UNCERTAIN ENTITY_CONFLICT NAMED_ENTITY_REJECT",
    "ARCHIVE_RETRIEVAL": "FOUNDER_ARCHIVE_MISSING PERSON_ARCHIVE_MISSING ARCHIVE_NOT_FOUND ARCHIVE_VERIFY_FAILED",
    "PROCESS_VISUAL": "PROCESS_ENTITY_MISMATCH PROCESS_VISUAL_MISSING GENERIC_PROCESS_AS_ENTITY GENERIC_PROCESS_AS_EVIDENCE",
    "PROVENANCE": "LICENSE_UNKNOWN SOURCE_URL_MISSING ATTRIBUTION_INVALID PROVENANCE_INCOMPLETE",
    "CAPTION": "CAPTION_END_EARLY CAPTION_MISSING CAPTION_RENDER_FAILURE CAPTION_SAFE_AREA_FAILURE",
    "GRAPHIC_DENSITY": "GRAPHIC_TEXT_TOO_SMALL GRAPHIC_DENSITY_FAILURE GRAPHIC_READABILITY_FAILURE",
    "TIMELINE": "VISUAL_END_EARLY FROZEN_TAIL EDL_GAP MUX_DURATION_MISMATCH",
    "STORY": "STORY_QUALITY_FAIL STORY_CONSISTENCY_FAIL UNSUPPORTED_CENTRAL_CLAIM TOPIC_PREFLIGHT_REJECT",
    "VLM_RATE_LIMIT": "VLM_RATE_LIMIT VLM_UNAVAILABLE VLM_TIMEOUT VISION_PROVIDER_FAILURE",
    "GENERIC_BROLL": "UNRELATED_STOCK GENERIC_FILLER GENERIC_BROLL_DOMINANT WEAK_VISUAL_ALIGNMENT",
}
CODE_CLUSTER = {code: cluster for cluster, codes in FAILURE_CODES.items() for code in codes.split()}
CLUSTER_PRIORITY = (
    ("ENTITY_SELECTION", "PROVENANCE"),
    ("STORY", "PROCESS_VISUAL"),
    ("TIMELINE", "CAPTION", "GRAPHIC_DENSITY"),
    ("GENERIC_BROLL", "ARCHIVE_RETRIEVAL"),
    ("VLM_RATE_LIMIT",),
    ("UNCLASSIFIED",),
)
DIMENSION_LABELS = (
    "Factual quality", "Story quality", "Entity safety", "Visual coverage",
    "Evidence integrity", "Provenance", "No slideshow", "Caption quality",
    "Timeline integrity", "Final human quality",
)
ARTIFACT_KINDS = ("EDL", "MANIFEST", "TRACE", "ATTRIBUTION")
STEM = "DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY"


def classify_failures(codes: list[str]) -> tuple[str, list[str]]:
    clusters = {CODE_CLUSTER.get(code, "UNCLASSIFIED") for code in codes if code}
    rank = {cluster: index for index, group in enumerate(CLUSTER_PRIORITY) for cluster in group}
    ordered = sorted(clusters, key=lambda cluster: (rank[cluster], cluster))
    return (ordered[0] if ordered else "", ordered)


def read_human_review(path: Path) -> dict:
    if not Path(path).is_file():
        return {"completed": False, "decision": "NOT_RUN", "quality": "NOT_RUN", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    fields = dict(line.split(":", 1) for line in lines if ":" in line and not line.lstrip().startswith("-"))
    fields = {key.strip(): value.strip() for key, value in fields.items()}
    decision = fields.get("Decision", "NOT_RUN").upper()
    quality = fields.get("Quality", "NOT_RUN").upper()
    manual_text = fields.get("Manual intervention required", "NOT_RUN").lower()
    dimensions = {key: fields.get(key, "NOT_RUN").upper() for key in DIMENSION_LABELS}
    complete = (
        decision in {"PASS", "FAIL"}
        and quality in {"PREMIUM", "GOOD", "ACCEPTABLE", "WEAK"}
        and manual_text in {"true", "false"}
        and all(value != "NOT_RUN" for value in dimensions.values())
    )
    findings = [line.strip()[2:] for line in lines if line.strip().startswith("- [")]
    return {
        "completed": complete, "decision": decision, "quality": quality,
        "manual_intervention_required": manual_text == "true",
        "findings": findings, "dimensions": dimensions,
    }


def evaluate_canary_job(package: dict, review: dict) -> dict:
    metrics = package.get("metrics") or {}
    gates = package.get("gates") or {}
    codes = list(metrics.get("failure_codes") or [])
    paths = package.get("paths") or {}
    mp4 = paths.get("mp4")
    produced = bool(mp4 and Path(mp4).is_file())
    attribution_path = paths.get("attribution")
    if attribution_path:
        try:
            attribution = json.loads(Path(attribution_path).read_text(encoding="utf-8"))
            entries = attribution.get("data") if isinstance(attribution, dict) else None
            if isinstance(attribution, dict) and attribution.get("artifact_status") == "NOT_PRODUCED" and not produced:
                pass
            elif not isinstance(entries, list) or not entries:
                codes.append("PROVENANCE_INCOMPLETE")
            else:
                for item in entries:
                    if not isinstance(item, dict):
                        codes.append("ATTRIBUTION_INVALID")
                    elif not item.get("internal") and not str(item.get("source_url") or "").strip():
                        codes.append("SOURCE_URL_MISSING")
                    if isinstance(item, dict) and str(item.get("license") or "UNKNOWN") in {"UNKNOWN", "RESTRICTED", "PROPRIETARY"}:
                        codes.append("LICENSE_UNKNOWN")
        except (OSError, ValueError):
            codes.append("ATTRIBUTION_INVALID")
    elif produced:
        codes.append("PROVENANCE_INCOMPLETE")
    error = package.get("error")
    if error:
        codes.append(error if error in CODE_CLUSTER else "UNCLASSIFIED")
    if metrics.get("remote_vision_available") is False and (
        not package.get("error") or package.get("failed_at") == "preflight"
    ):
        codes.append("VLM_UNAVAILABLE")
    if metrics.get("uncovered_important_beats"):
        codes.append("PROCESS_VISUAL_MISSING")
    if (metrics.get("critic") or {}).get("unresolved_high", 0):
        codes.append("STORY_QUALITY_FAIL")
    primary, clusters = classify_failures(codes)
    completed = bool(review.get("completed"))
    manual = bool(review.get("manual_intervention_required") or metrics.get("manual_intervention_required"))
    all_gates_pass = all(gates.get(name) == "PASS" for name in MANDATORY_GATES)
    high_findings = any("HIGH" in str(item).upper() for item in review.get("findings") or [])
    hard_fail = bool(error or codes or not all_gates_pass or high_findings)
    infrastructure_blocked = bool(
        error and any(token in str(error) for token in (
            "HTTPConnectionPool", "Connection refused", "WinError 10061",
            "VLM_UNAVAILABLE", "VLM_RATE_LIMIT", "VISION_PROVIDER_FAILURE",
            "missing_text_llm_key",
        ))
    )
    accepted = (
        produced and completed and review.get("decision") == "PASS"
        and not manual and not hard_fail
    )
    return {
        **package,
        "mp4_produced": produced,
        "human_review_completed": completed,
        "human_decision": review.get("decision", "NOT_RUN"),
        "human_quality": review.get("quality", "NOT_RUN"),
        "human_dimensions": review.get("dimensions") or {},
        "manual_intervention_required": manual,
        "counts_as_autonomous_evidence": accepted,
        "automated_verdict": "FAIL" if hard_fail else ("PASS" if accepted else "REVIEW_REQUIRED"),
        "failure_codes": codes,
        "primary_cluster": primary,
        "all_clusters": clusters,
        "infrastructure_blocked": infrastructure_blocked,
    }


def load_suite(path: Path) -> list[dict]:
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("suite must be a list")
    types = []
    for entry in entries:
        if not isinstance(entry, dict) or any(
            not entry.get(key) for key in ("topic", "story_type", "selection_rationale", "dimensions")
        ):
            raise ValueError("suite entry requires topic, story_type, selection_rationale, dimensions")
        if not isinstance(entry["dimensions"], list):
            raise ValueError("dimensions must be a list")
        types.append(entry["story_type"])
    if len(types) != 5 or set(types) != STORY_TYPES:
        raise ValueError("suite requires five distinct story_type categories")
    return entries


def write_stage_g_package(
    job_dir: Path, job_id: str, result: StageFResult | None, *,
    failed_at: str | None, error: str | None, gates: dict, clusters: list[str],
) -> dict[str, Path]:
    job_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for kind in ARTIFACT_KINDS:
        source = Path(getattr(result, f"{kind.lower()}_path", "")) if result and getattr(result, f"{kind.lower()}_path", "") else None
        payload = None
        read_error = None
        if source:
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                read_error = f"artifact_read_failed:{type(exc).__name__}"
        dest = job_dir / f"{STEM}_{kind}_{job_id}.json"
        dest.write_text(json.dumps({
            "stage_g_job_id": job_id,
            "source_artifact": str(source) if source else None,
            "artifact_status": "PRODUCED" if payload is not None else "NOT_PRODUCED",
            "failed_at": failed_at,
            "error": read_error or error,
            "gates": gates,
            "failure_clusters": clusters,
            "metrics": result.metrics if result else {},
            "data": payload,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        paths[kind.lower()] = dest
    review = job_dir / f"{STEM}_HUMAN_REVIEW_{job_id}.md"
    review.write_text(
        f"# Stage G human review: {job_id}\n\n"
        "Decision: NOT_RUN\nQuality: NOT_RUN\nManual intervention required: NOT_RUN\n"
        "\n## Dimension decisions\n\n"
        + "".join(f"{label}: NOT_RUN\n" for label in DIMENSION_LABELS)
        + "\n## Timestamped findings\n\n"
        "Watch the complete produced MP4 before recording a decision.\n",
        encoding="utf-8",
    )
    paths["human_review"] = review
    if result and result.output_mp4:
        source_mp4 = Path(result.output_mp4)
        if source_mp4.is_file() and source_mp4.resolve().is_relative_to(job_dir.resolve()):
            dest_mp4 = job_dir / f"{STEM}_{job_id}.mp4"
            source_mp4.rename(dest_mp4)
            paths["mp4"] = dest_mp4
    return paths


def run_canary_job(
    entry: dict, output_root: Path, *, job_id: str,
    max_job_elapsed_sec: float, publish: bool = False,
) -> dict:
    if publish:
        raise ValueError("Stage G cannot publish")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise ValueError("job_id must be path-safe")
    if any(not entry.get(key) for key in ("topic", "story_type", "selection_rationale", "dimensions")):
        raise ValueError("invalid suite entry")
    if resolve_pipeline_mode(canary=True) != PipelineMode.DOCUMENTARY_V2_CANARY:
        raise RuntimeError("explicit canary mode unavailable")
    job_dir = Path(output_root) / job_id
    if job_dir.exists():
        raise FileExistsError(job_dir)
    job_dir.mkdir(parents=True)
    result = None
    error = None
    failed_at = None
    try:
        result = run_topic_review(
            entry["topic"], job_dir, job_id=job_id,
            max_job_elapsed_sec=max_job_elapsed_sec, publish=False,
            canary_preflight=True,
        )
        error = result.error or None
        failed_at = result.metrics.get("failed_at") or ("topic_review" if error else None)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"[:500]
        failed_at = "topic_review"
    if result and not error:
        for kind in ARTIFACT_KINDS:
            source_path = getattr(result, f"{kind.lower()}_path", "")
            if source_path:
                try:
                    json.loads(Path(source_path).read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    error = f"artifact_read_failed:{type(exc).__name__}"
                    failed_at = "artifact_normalization"
                    break
    failure_codes = list((result.metrics if result else {}).get("failure_codes") or [])
    if error:
        failure_codes.append(error if error in CODE_CLUSTER else "UNCLASSIFIED")
    _, clusters = classify_failures(failure_codes)
    paths = write_stage_g_package(
        job_dir, job_id, result, failed_at=failed_at, error=error,
        gates=result.gates if result else {}, clusters=clusters,
    )
    package = {
        "job_id": job_id, "topic": entry["topic"], "story_type": entry["story_type"],
        "selection_rationale": entry["selection_rationale"], "dimensions": entry["dimensions"],
        "error": error, "failed_at": failed_at,
        "gates": result.gates if result else {}, "metrics": result.metrics if result else {},
        "paths": {key: str(value) for key, value in paths.items()},
        "publish": False,
    }
    return evaluate_canary_job(package, read_human_review(paths["human_review"]))


def build_scorecard(jobs: list[dict], *, test_set_exhausted: bool) -> dict:
    accepted = [
        job for job in jobs
        if job.get("counts_as_autonomous_evidence")
        and job.get("mp4_produced")
        and job.get("human_review_completed")
        and job.get("human_decision") == "PASS"
        and not job.get("manual_intervention_required")
        and not job.get("failure_codes")
        and not job.get("error")
    ]
    story_types = {job.get("story_type") for job in accepted}
    high_quality = [job for job in accepted if job.get("human_quality") in {"GOOD", "PREMIUM"}]
    pending = [job for job in jobs if job.get("mp4_produced") and not job.get("human_review_completed")]
    creative_clusters = set(CODE_CLUSTER.values()) - {"VLM_RATE_LIMIT", "UNCLASSIFIED"}
    cluster_types: dict[str, set[str]] = defaultdict(set)
    for job in jobs:
        for cluster in job.get("all_clusters") or []:
            if cluster in creative_clusters:
                cluster_types[cluster].add(job.get("story_type", ""))
    systemic = any(len(types) >= 2 for types in cluster_types.values())
    creative_failure = any(
        not job.get("counts_as_autonomous_evidence")
        and not job.get("human_review_completed")
        and not job.get("mp4_produced")
        and bool(set(job.get("all_clusters") or []) & creative_clusters)
        for job in jobs
    )
    safety_defect = any(job.get("safety_boundary_violation") for job in jobs)
    pass_ready = (
        len(accepted) >= 3 and len(story_types) >= 3
        and len(high_quality) / len(accepted) > 0.5
        and not safety_defect
    )
    infrastructure_count = sum(bool(job.get("infrastructure_blocked")) for job in jobs)
    infrastructure_majority = bool(jobs and infrastructure_count > len(jobs) / 2)
    fail = (
        (not accepted and creative_failure) or systemic or safety_defect
        or (test_set_exhausted and not accepted and not infrastructure_majority)
    )
    failed_primaries = Counter(job.get("primary_cluster") for job in jobs if job.get("primary_cluster") and not job.get("counts_as_autonomous_evidence"))
    most_common = failed_primaries.most_common(2)
    infrastructure_main = infrastructure_majority or bool(most_common and most_common[0][0] == "VLM_RATE_LIMIT" and (len(most_common) == 1 or most_common[0][1] > most_common[1][1]))
    if pass_ready:
        decision = "CANARY_PASS"
    elif fail:
        decision = "CANARY_FAIL"
    elif accepted or pending or infrastructure_main:
        decision = "CANARY_PARTIAL"
    else:
        decision = "PENDING"
    dimensions = {label: [job.get("human_dimensions", {}).get(label, "NOT_RUN") for job in jobs] for label in DIMENSION_LABELS}
    vlm_calls = [job.get("metrics", {}).get("critic", {}).get("vlm_calls") for job in jobs]
    costs = [job.get("metrics", {}).get("critic", {}).get("estimated_cost_usd") for job in jobs]
    durations = [job.get("metrics", {}).get("duration") for job in jobs]
    matrix = [{
        "job_id": job.get("job_id"), "story_type": job.get("story_type"),
        "mp4_produced": bool(job.get("mp4_produced")),
        "human_decision": job.get("human_decision", "NOT_RUN"),
        "human_quality": job.get("human_quality", "NOT_RUN"),
        "manual_intervention_required": bool(job.get("manual_intervention_required")),
        "counts_as_autonomous_evidence": bool(job.get("counts_as_autonomous_evidence")),
        "primary_cluster": job.get("primary_cluster", ""),
        "all_clusters": job.get("all_clusters") or [],
    } for job in jobs]
    return {
        "decision": decision, "test_set_exhausted": test_set_exhausted,
        "job_count": len(jobs), "autonomous_accepted_count": len(accepted),
        "distinct_accepted_story_types": sorted(story_types),
        "high_quality_accepted_count": len(high_quality),
        "pending_human_count": len(pending),
        "infrastructure_blocked_count": infrastructure_count,
        "manual_intervention_count": sum(bool(job.get("manual_intervention_required")) for job in jobs),
        "failure_clusters": dict(Counter(cluster for job in jobs for cluster in job.get("all_clusters") or [])),
        "dimensions": dimensions,
        "generalization_matrix": matrix,
        "vlm_activity": {"critic_calls": sum(value for value in vlm_calls if isinstance(value, (int, float))), "known_jobs": sum(value is not None for value in vlm_calls)},
        "costs": {"known_critic_usd": sum(value for value in costs if isinstance(value, (int, float))) if any(value is not None for value in costs) else None},
        "averages": {"duration_sec": mean(value for value in durations if isinstance(value, (int, float))) if any(isinstance(value, (int, float)) for value in durations) else None},
        "jobs": jobs,
    }


def write_aggregate(scorecard: dict, output_root: Path) -> tuple[Path, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    score_path = output_root / "DOCUMENTARY_ENGINE_V2_STAGE_G_SCORECARD.json"
    report_path = output_root / "DOCUMENTARY_ENGINE_V2_STAGE_G_REPORT.md"
    score_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    rows = [
        "# Documentary Engine V2 Stage G Canary Report", "",
        f"Decision: {scorecard['decision']}",
        f"Jobs: {scorecard['job_count']}",
        f"Autonomous accepted: {scorecard['autonomous_accepted_count']}",
        f"Distinct accepted story types: {len(scorecard['distinct_accepted_story_types'])}",
        f"Pending human review: {scorecard['pending_human_count']}",
        f"Infrastructure blocked: {scorecard['infrastructure_blocked_count']}",
        "", "## Jobs", "",
    ]
    for job in scorecard["jobs"]:
        rows.append(
            f"- `{job.get('job_id')}` — {job.get('story_type')}: "
            f"{job.get('automated_verdict', 'REVIEW_REQUIRED')}; "
            f"human {job.get('human_decision', 'NOT_RUN')}; "
            f"cluster {job.get('primary_cluster') or 'NONE'}; "
            f"error {job.get('error') or 'NONE'}"
        )
    rows.extend(["", "Human acceptance requires watching each produced MP4. No result enables publishing or global V2.", ""])
    report_path.write_text("\n".join(rows), encoding="utf-8")
    return report_path, score_path
