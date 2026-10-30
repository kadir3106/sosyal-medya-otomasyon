import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import config
from app.main import _run_parallel_uploads, app

client = TestClient(app)


def test_run_parallel_uploads_timeout_is_unknown_not_error():
    """A timed-out upload may still have published; it must not be reported as a failure."""

    def slow(name):
        time.sleep(0.3)
        return {"platform": name, "status": "success"}

    with patch("app.main._PUBLISH_TIMEOUT_SECONDS", 0.05):
        results = _run_parallel_uploads([("youtube", slow, ("youtube",), {})])

    assert results[0]["status"] == "unknown"
    assert "unknown" in results[0]["error"]


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
