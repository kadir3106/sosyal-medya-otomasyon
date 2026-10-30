import json
from pathlib import Path

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


def test_concurrent_appends_do_not_lose_entries(tmp_path):
    """Regression: unlocked read-modify-write dropped most entries.

    Measured before the fix: 40 concurrent appends stored 5 entries (35 lost) and
    the file ended up as invalid JSON. Parallel publish results all write here.
    """
    import threading

    log_path = str(tmp_path / "log.json")
    n = 40
    threads = [
        threading.Thread(
            target=append_publish_log,
            args=(log_path, {"published_at": "2026-09-03T09:00:00+00:00", "n": i}),
        )
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = json.loads(Path(log_path).read_text(encoding="utf-8"))
    assert len(entries) == n
    assert sorted(e["n"] for e in entries) == list(range(n))


def test_append_recovers_from_corrupt_file_without_losing_it(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text("{not json", encoding="utf-8")

    append_publish_log(str(log_path), {"published_at": "2026-09-03T09:00:00+00:00", "n": 1})

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert entries == [{"published_at": "2026-09-03T09:00:00+00:00", "n": 1}]
    # The damaged content is preserved next to the file instead of being discarded.
    assert log_path.with_suffix(".json.corrupt").read_text(encoding="utf-8") == "{not json"
