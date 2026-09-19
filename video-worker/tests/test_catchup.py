from datetime import date, datetime

from app.catchup import mark_run_today, maybe_catch_up, past_scheduled_hour, ran_today


def test_ran_today_false_when_marker_missing(tmp_path):
    assert ran_today(str(tmp_path / "marker.txt")) is False


def test_mark_and_ran_today_round_trip(tmp_path):
    marker = str(tmp_path / "marker.txt")
    fixed_day = date(2026, 9, 5)

    mark_run_today(marker, today=fixed_day)

    assert ran_today(marker, today=fixed_day) is True
    assert ran_today(marker, today=date(2026, 9, 6)) is False


def test_past_scheduled_hour():
    assert past_scheduled_hour(9, now=datetime(2026, 9, 5, 9, 0)) is True
    assert past_scheduled_hour(9, now=datetime(2026, 9, 5, 14, 30)) is True
    assert past_scheduled_hour(9, now=datetime(2026, 9, 5, 8, 59)) is False


async def _noop():
    return {"ok": True}


async def test_maybe_catch_up_skips_when_pending_job_exists(tmp_path):
    (tmp_path / "pending.json").write_text("{}", encoding="utf-8")
    calls = []

    async def video_fn():
        calls.append("video")

    result = await maybe_catch_up(
        str(tmp_path), 9, 12, video_fn, _noop, now=datetime(2026, 9, 5, 15, 0)
    )

    assert result is None
    assert calls == []


async def test_maybe_catch_up_triggers_video_when_missed_and_past_hour(tmp_path):
    calls = []

    async def video_fn():
        calls.append("video")

    async def image_fn():
        calls.append("image")

    result = await maybe_catch_up(
        str(tmp_path), 9, 12, video_fn, image_fn, now=datetime(2026, 9, 5, 10, 0)
    )

    assert result == "video"
    assert calls == ["video"]


async def test_maybe_catch_up_falls_through_to_image_when_video_already_ran(tmp_path):
    mark_run_today(str(tmp_path / "last_video_run.txt"), today=date(2026, 9, 5))
    calls = []

    async def video_fn():
        calls.append("video")

    async def image_fn():
        calls.append("image")

    result = await maybe_catch_up(
        str(tmp_path), 9, 12, video_fn, image_fn, now=datetime(2026, 9, 5, 13, 0)
    )

    assert result == "image"
    assert calls == ["image"]


async def test_maybe_catch_up_does_nothing_when_both_already_ran(tmp_path):
    mark_run_today(str(tmp_path / "last_video_run.txt"), today=date(2026, 9, 5))
    mark_run_today(str(tmp_path / "last_image_run.txt"), today=date(2026, 9, 5))
    calls = []

    async def video_fn():
        calls.append("video")

    async def image_fn():
        calls.append("image")

    result = await maybe_catch_up(
        str(tmp_path), 9, 12, video_fn, image_fn, now=datetime(2026, 9, 5, 18, 0)
    )

    assert result is None
    assert calls == []


async def test_maybe_catch_up_does_nothing_before_scheduled_hour(tmp_path):
    calls = []

    async def video_fn():
        calls.append("video")

    async def image_fn():
        calls.append("image")

    result = await maybe_catch_up(
        str(tmp_path), 9, 12, video_fn, image_fn, now=datetime(2026, 9, 5, 8, 0)
    )

    assert result is None
    assert calls == []
