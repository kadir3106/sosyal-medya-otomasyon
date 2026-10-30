import re
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import config
from app.main import _PUBLISH_TIMEOUT_SECONDS, _run_parallel_uploads, app

client = TestClient(app)


def test_publish_budget_exceeds_every_publisher_request_timeout():
    """A budget below a publisher's own request timeout would abort a live request.

    Regression: the budget was 300s while youtube/tiktok/meta upload the video body
    with timeout=600, so those uploads were guaranteed to be cut off and reported as
    a false "unknown" outcome.
    """
    publishers = Path(__file__).resolve().parent.parent / "app" / "publishers"
    worst = 0
    for path in publishers.glob("*.py"):
        if "browser" in path.name:
            # tiktok_browser is host-only (not in the publish fan-out) and its
            # timeout= values are Playwright DOM waits in milliseconds.
            continue
        for raw in re.findall(r"timeout=(\d+)", path.read_text(encoding="utf-8")):
            worst = max(worst, int(raw))

    assert worst > 0, "publisher timeouts not detected; the guard would be vacuous"
    assert _PUBLISH_TIMEOUT_SECONDS > worst, (
        f"publish budget {_PUBLISH_TIMEOUT_SECONDS}s must exceed the largest "
        f"publisher request timeout {worst}s"
    )


def test_run_parallel_uploads_timeout_is_unknown_not_error():
    """A genuinely stuck upload must not be reported as a failure."""

    def stuck(name):
        time.sleep(5)
        return {"platform": name, "status": "success"}

    with patch("app.main._PUBLISH_TIMEOUT_SECONDS", 0.05):
        results = _run_parallel_uploads([("youtube", stuck, ("youtube",), {})])

    assert results[0]["status"] == "unknown"
    assert "unknown" in results[0]["error"]


def test_run_parallel_uploads_reads_settled_result_within_deadline():
    """Regression: pool shutdown must not hide a finished upload behind a timeout.

    With `with ThreadPoolExecutor(...)`, exiting the block called shutdown(wait=True),
    so fut.result(timeout=...) expiry still waited for the worker. The upload really
    completed while the caller reported "unknown".
    """

    def completes_quickly(name):
        time.sleep(0.05)
        return {"platform": name, "status": "success", "video_id": "vid1"}

    started = time.monotonic()
    with patch("app.main._PUBLISH_TIMEOUT_SECONDS", 1.0):
        results = _run_parallel_uploads(
            [("youtube", completes_quickly, ("youtube",), {})]
        )
    elapsed = time.monotonic() - started

    assert results[0]["status"] == "success"
    assert results[0]["video_id"] == "vid1"
    assert elapsed < 1.0, "must not wait for the whole deadline when the task settles"


def test_run_parallel_uploads_real_exception_still_error():
    def boom(name):
        raise RuntimeError("api said no")

    results = _run_parallel_uploads([("youtube", boom, ("youtube",), {})])

    assert results[0]["status"] == "error"
    assert "api said no" in results[0]["error"]


@patch("app.main.upload_to_linkedin")
@patch("app.main.upload_to_x")
def test_publish_timeout_does_not_offer_blind_retry(mock_x, mock_li, tmp_path):
    """Regression: a timed-out upload must not write a retry sidecar.

    The worker thread keeps running after fut.result() times out and may have
    published. Offering "Tekrar dene" would post the same video a second time.
    """
    from app import jobs as job_store

    image_path = tmp_path / "jobtimeout.png"
    image_path.write_bytes(b"BYTES")
    job_store.create_job(tmp_path, "jobtimeout", kind="image", state="awaiting_approval")

    def slow_upload(*args, **kwargs):
        time.sleep(0.3)
        return {"platform": "x", "status": "success", "tweet_id": "t1"}

    mock_x.side_effect = slow_upload
    mock_li.side_effect = slow_upload

    body = {
        "kind": "image",
        "image_path": str(image_path),
        "image_filename": "jobtimeout.png",
        "caption": "timeout guard",
    }
    with patch.object(config, "MEDIA_DIR", str(tmp_path)), patch(
        "app.main._PUBLISH_TIMEOUT_SECONDS", 0.05
    ):
        response = client.post("/publish", json=body)

    assert response.status_code == 502
    assert "unknown" in response.json()["detail"].lower()
    # No retry sidecar, and the file is kept so the operator can inspect it.
    assert not (tmp_path / "failed" / "jobtimeout.json").exists()
    assert image_path.is_file()
    assert job_store.get_job(tmp_path, "jobtimeout")["state"] == "failed"
