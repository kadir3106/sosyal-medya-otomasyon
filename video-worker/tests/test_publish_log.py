import json

from app.publish_log import append_publish_log, load_recent_entries


def test_append_publish_log_creates_file_when_missing(tmp_path):
    log_path = tmp_path / "log.json"

    append_publish_log(
        str(log_path), {"published_at": "2026-09-03T09:00:00+00:00", "title": "A"}
    )

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert entries == [{"published_at": "2026-09-03T09:00:00+00:00", "title": "A"}]


def test_append_publish_log_appends_to_existing_file(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps([{"published_at": "2026-09-01T09:00:00+00:00", "title": "Old"}]),
        encoding="utf-8",
    )

    append_publish_log(
        str(log_path), {"published_at": "2026-09-03T09:00:00+00:00", "title": "New"}
    )

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[1]["title"] == "New"


def test_load_recent_entries_filters_by_date(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps(
            [
                {"published_at": "2026-08-20T09:00:00+00:00", "title": "TooOld"},
                {"published_at": "2026-09-02T09:00:00+00:00", "title": "Recent"},
            ]
        ),
        encoding="utf-8",
    )

    result = load_recent_entries(str(log_path), since_iso="2026-08-27T00:00:00+00:00")

    assert [e["title"] for e in result] == ["Recent"]


def test_load_recent_entries_returns_empty_when_file_missing(tmp_path):
    result = load_recent_entries(
        str(tmp_path / "missing.json"), since_iso="2026-08-27T00:00:00+00:00"
    )
    assert result == []
