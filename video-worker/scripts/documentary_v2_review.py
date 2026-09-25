"""CLI for a single unpublished Documentary Engine V2 review package."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.documentary_v2.review_runner import run_topic_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an unpublished V2 review MP4 from one topic")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--max-job-elapsed-sec", type=float, default=360.0)
    args = parser.parse_args()
    result = run_topic_review(
        args.topic, args.media_dir, job_id=args.job_id,
        max_job_elapsed_sec=args.max_job_elapsed_sec,
    )
    print(f"Verdict: {result.metrics.get('automated_verdict', 'FAIL')}")
    print(f"Review report: {result.report_path}")
    print(f"Review MP4: {result.output_mp4 or 'not produced'}")
    return 0 if result.metrics.get("automated_verdict") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
