"""Optional Remotion bridge for Stage E motion graphics.

Primary renderer is internal PIL+FFmpeg (works in video-worker without Node).
This module documents how Remotion can be invoked later as a specialized
renderer without becoming the full documentary engine.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.documentary_v2.schemas import MotionGraphicPlan


def remotion_pipeline_dir() -> Path | None:
    try:
        from app.config import config

        root = Path(config.MEDIA_DIR).resolve().parent
        cand = root / "remotion-pipeline"
        return cand if cand.is_dir() else None
    except Exception:
        return None


def export_plan_props(plan: MotionGraphicPlan) -> dict:
    """Props payload a future Remotion DocumentaryPrimitive composition would accept."""
    return {
        "primitive": plan.primitive,
        "nodes": plan.nodes,
        "relationships": plan.relationships,
        "events": plan.events,
        "labels": plan.labels,
        "claimIds": plan.claim_ids,
        "evidenceIds": plan.evidence_ids,
        "durationSec": plan.duration or 3.0,
        "themeId": plan.theme_id,
        "explanatoryOnly": plan.explanatory_only,
        "mapLocation": plan.map_location,
    }


def try_remotion_render(plan: MotionGraphicPlan, *, output_path: str) -> tuple[bool, str]:
    """Best-effort Remotion CLI render. Returns (ok, message). Does not raise."""
    root = remotion_pipeline_dir()
    if root is None:
        return False, "remotion_pipeline_missing"
    props_path = Path(output_path).with_suffix(".props.json")
    props_path.write_text(json.dumps(export_plan_props(plan)), encoding="utf-8")
    # Composition id reserved for Stage E+. Not required for Stage E acceptance
    # because internal renderer produces the validated clip.
    cmd = [
        "npx.cmd" if Path("C:/").exists() else "npx",
        "remotion",
        "render",
        "src/index.ts",
        "DocumentaryPrimitive",
        output_path,
        f"--props={props_path}",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout or "remotion_failed")[-400:]
        return True, output_path
    except Exception as exc:
        return False, str(exc)[:300]
