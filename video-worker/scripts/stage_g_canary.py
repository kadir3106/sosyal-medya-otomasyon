"""Explicit, non-publishing Stage G canary CLI."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.documentary_v2.canary import (
    build_scorecard, evaluate_canary_job, load_suite, read_human_review,
    run_canary_job, write_aggregate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run five unpublished Stage G canaries")
    parser.add_argument("--suite", type=Path, default=Path(__file__).resolve().parents[1] / "app/documentary_v2/stage_g_suite.json")
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[1] / "video-output/stage_g")
    parser.add_argument("--max-job-elapsed-sec", type=float, default=360.0)
    parser.add_argument("--refresh-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if args.publish:
        parser.error("Stage G cannot publish")
    if args.max_job_elapsed_sec <= 0:
        parser.error("max-job-elapsed-sec must be positive")
    entries = load_suite(args.suite)
    if args.refresh_only:
        import json
        score_path = args.output_root / "DOCUMENTARY_ENGINE_V2_STAGE_G_SCORECARD.json"
        prior = json.loads(score_path.read_text(encoding="utf-8"))
        jobs = [evaluate_canary_job(job, read_human_review(Path(job["paths"]["human_review"]))) for job in prior["jobs"]]
    else:
        jobs = []
        for entry in entries:
            job_id = f"sg{datetime.now(timezone.utc):%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:8]}"
            jobs.append(run_canary_job(entry, args.output_root, job_id=job_id, max_job_elapsed_sec=args.max_job_elapsed_sec, publish=False))
            write_aggregate(build_scorecard(jobs, test_set_exhausted=False), args.output_root)
    report, score = write_aggregate(build_scorecard(jobs, test_set_exhausted=len(jobs) >= len(entries)), args.output_root)
    print(f"Report: {report}\nScorecard: {score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
