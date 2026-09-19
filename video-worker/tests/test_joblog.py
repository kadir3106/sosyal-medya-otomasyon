import json

from app.joblog import log_event


def test_log_event_prints_correlated_json(capsys):
    log_event("job123", "render_done", seconds=4.2, extra="x")

    captured = json.loads(capsys.readouterr().out.strip())
    assert captured["job_id"] == "job123"
    assert captured["stage"] == "render_done"
    assert captured["seconds"] == 4.2
    assert captured["extra"] == "x"
    assert "ts" in captured
