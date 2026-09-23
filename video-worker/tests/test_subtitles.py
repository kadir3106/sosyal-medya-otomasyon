from app.subtitles import write_ass


def test_write_ass_groups_words_into_karaoke_bursts(tmp_path):
    # offset/duration 100-nanosecond units: 10_000_000 == 1 second
    boundaries = [
        {"offset": 0, "duration": 10_000_000, "text": "Flamingos"},
        {"offset": 10_000_000, "duration": 10_000_000, "text": "stand"},
        {"offset": 20_000_000, "duration": 10_000_000, "text": "on"},
        {"offset": 30_000_000, "duration": 10_000_000, "text": "one"},
        {"offset": 40_000_000, "duration": 10_000_000, "text": "leg"},
    ]
    output_path = tmp_path / "subs.ass"

    result = write_ass(boundaries, str(output_path), words_per_cue=2)

    assert result == str(output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert (
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Flamingos stand" in content
    )
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,on one" in content
    assert "Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,leg" in content


def test_write_ass_handles_empty_boundaries(tmp_path):
    output_path = tmp_path / "subs.ass"

    result = write_ass([], str(output_path))

    assert result == str(output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "[Events]" in content
    assert "Dialogue:" not in content


def test_write_ass_formats_hours_and_centiseconds(tmp_path):
    boundaries = [
        {"offset": 36_615_000_000, "duration": 5_000_000, "text": "late"},
    ]
    output_path = tmp_path / "subs.ass"

    write_ass(boundaries, str(output_path), words_per_cue=1)

    content = output_path.read_text(encoding="utf-8")
    assert "Dialogue: 0,1:01:01.50,1:01:02.00,Default,,0,0,0,,late" in content


def test_write_ass_escapes_special_characters(tmp_path):
    boundaries = [
        {"offset": 0, "duration": 1_000_000, "text": "{weird}"},
        {"offset": 1_000_000, "duration": 1_000_000, "text": "back\\slash"},
    ]
    output_path = tmp_path / "subs.ass"

    write_ass(boundaries, str(output_path), words_per_cue=2)

    content = output_path.read_text(encoding="utf-8")
    assert "{weird}" not in content
    assert "(weird) back\\\\slash" in content


def test_write_ass_with_karaoke_highlight(tmp_path):
    boundaries = [
        {"offset": 0, "duration": 10_000_000, "text": "Hızlı"},
        {"offset": 10_000_000, "duration": 10_000_000, "text": "para"},
    ]
    output_path = tmp_path / "subs_highlight.ass"

    write_ass(boundaries, str(output_path), words_per_cue=2, highlight=True, add_emojis=True)

    content = output_path.read_text(encoding="utf-8")
    # Vurgu etiketi altın renk: \c&H0000D7FF& ve metin beyazı: \c&H00F8F9FA&
    assert r"{\c&H0000D7FF&}HIZLI{\c&H00F8F9FA&} PARA" in content
    assert r"HIZLI {\c&H0000D7FF&}PARA{\c&H00F8F9FA&}" in content
    # Emojiler entegre edilmiş olmalı (para -> 💰)
    assert "💰" in content


def test_write_ass_hook_overlay_on_first_seconds(tmp_path):
    boundaries = [
        {"offset": 0, "duration": 10_000_000, "text": "Hello"},
    ]
    output_path = tmp_path / "subs.ass"
    write_ass(
        boundaries,
        str(output_path),
        hook_text="Your engagement ring is worth zero dollars",
        hook_seconds=2.5,
    )
    content = output_path.read_text(encoding="utf-8")
    assert "Style: Hook," in content
    # Phase 2.2: capped ≤1.8s with fade
    assert ",Hook," in content
    assert r"\fad(" in content
    assert "engagement ring" in content.lower()

