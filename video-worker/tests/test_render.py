from unittest.mock import patch, Mock

import pytest

from app.render import (
    build_scene_sources,
    clip_reuse_ratio,
    get_audio_duration,
    plan_scene_schedule,
    render_video,
    scene_transition_times,
)


def test_plan_scene_schedule_covers_full_audio_without_looping():
    """Sahne planı ses süresini tam kaplar — fazlalık başa sarılarak değil."""
    durations = plan_scene_schedule(30.888, base_duration=2.2, xfade_duration=0.4)

    # 30.888 sn ses -> sabit 6 sahne DEĞİL, ses süresine yetecek kadar sahne.
    assert len(durations) >= 14
    covered = sum(durations) - 0.4 * (len(durations) - 1)
    assert covered == pytest.approx(30.888, abs=0.02)


def test_plan_scene_schedule_uses_variable_rhythm():
    """Kanca hızlı, anlatı normal, kapanış geniş — tek düze süre yok."""
    durations = plan_scene_schedule(30.0, base_duration=2.2, xfade_duration=0.4)

    assert durations[0] == 1.6  # kanca hızlı kesilir
    assert len(set(durations)) > 1  # süreler tek düze değil
    assert max(durations) >= 2.6  # final sahnesi nefes alır


def test_plan_scene_schedule_single_scene_for_short_audio():
    """Çok kısa ses -> tek sahne, ve sahne ses süresine göre kısaltılır."""
    assert plan_scene_schedule(0.8, base_duration=2.2, xfade_duration=0.4) == [1.2]


def test_build_scene_sources_never_repeats_same_clip_back_to_back():
    """Ham döngü ([a,b,a,b]) yerine komşusu farklı kaynak seçilir."""
    sources = build_scene_sources(["a.mp4", "b.mp4", "c.mp4"], 8)

    assert len(sources) == 8
    used = [path for path, _ in sources]
    assert all(used[i] != used[i + 1] for i in range(len(used) - 1))
    # Tüm klipler adil biçimde kullanılır (ilk klip aç kalmasın).
    assert used.count("a.mp4") == 3
    assert set(used) == {"a.mp4", "b.mp4", "c.mp4"}


def test_build_scene_sources_seeks_into_clip_on_reuse():
    """Tekrar kullanılan klip farklı bir saniyesinden başlatılır (yeni kare)."""
    sources = build_scene_sources(["solo.mp4"], 4)

    seeks = [seek for _, seek in sources]
    assert seeks == [0.0, 1.2, 2.4, 3.6]  # aynı kare 4 kez gösterilmez


def test_plan_scene_schedule_shrinks_scene_count_when_clips_are_scarce():
    """Klip azsa sahne sayısı kısılır: aynı kare defalarca dönmez."""
    unlimited = plan_scene_schedule(30.9, base_duration=2.2, xfade_duration=0.4)
    limited = plan_scene_schedule(
        30.9, base_duration=2.2, xfade_duration=0.4, max_scenes=8
    )

    assert len(limited) <= 8
    assert len(limited) < len(unlimited)
    # Ama hâlâ tüm ses süresini kaplar (sessiz donma yok).
    covered = sum(limited) - 0.4 * (len(limited) - 1)
    assert covered == pytest.approx(30.9, abs=0.6)
    # Sahne süreleri donuk kareye dönüşecek kadar uzamaz.
    assert max(limited) <= 6.0


def test_plan_scene_schedule_ignores_max_scenes_when_not_needed():
    """Tavan gereğinden yüksekse davranış değişmez."""
    assert plan_scene_schedule(
        30.9, base_duration=2.2, xfade_duration=0.4, max_scenes=99
    ) == plan_scene_schedule(30.9, base_duration=2.2, xfade_duration=0.4)


def test_render_video_limits_reuse_when_clips_are_scarce(tmp_path):
    """4 klip + 30 sn ses: ham döngü yerine sahne sayısı kısılır (tekrar ≤ 2x)."""
    with patch("app.render.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        clips = []
        for i in range(4):
            clip = tmp_path / f"clip_{i}.mp4"
            clip.write_bytes(b"A")
            clips.append(str(clip))

        stats: dict = {}
        with patch("app.render.get_audio_duration", return_value=30.9):
            render_video(
                clips,
                str(tmp_path / "speech.mp3"),
                str(tmp_path / "subs.ass"),
                str(tmp_path / "out.mp4"),
                str(tmp_path),
                clip_duration=2.2,
                xfade_duration=0.4,
                cinematic_grade=False,
                stats_out=stats,
            )

    assert stats["clip_reuse_ratio"] <= 2.0
    assert stats["scene_count"] <= 8


def test_clip_reuse_ratio_reports_excess_reuse():
    assert clip_reuse_ratio(["a.mp4"], 1) == 1.0
    assert clip_reuse_ratio(["a.mp4", "b.mp4"], 6) == 3.0
    assert clip_reuse_ratio([], 5) == 0.0


def test_scene_transition_times_match_xfade_offsets():
    """SFX zamanları render'ın gerçek geçiş anlarıyla birebir aynı olmalı."""
    durations = [1.6, 1.6, 1.6, 5.0, 2.4]

    times = scene_transition_times(durations, xfade_duration=0.4)

    assert times == [1.2, 2.4, 3.6, 8.2]


@patch("app.render.subprocess.run")
def test_get_audio_duration_parses_ffprobe_output(mock_run):
    mock_run.return_value = Mock(returncode=0, stdout="42.500000\n", stderr="")

    assert get_audio_duration("/tmp/speech.mp3") == 42.5

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ffprobe"
    assert "/tmp/speech.mp3" in cmd


@patch("app.render.subprocess.run")
def test_get_audio_duration_raises_on_ffprobe_failure(mock_run):
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="no such file")

    with pytest.raises(RuntimeError, match="ffprobe failed"):
        get_audio_duration("/tmp/missing.mp3")


def test_render_video_raises_when_no_clips(tmp_path):
    with pytest.raises(ValueError, match="at least one clip"):
        render_video(
            [],
            str(tmp_path / "a.mp3"),
            str(tmp_path / "s.srt"),
            str(tmp_path / "out.mp4"),
            str(tmp_path),
        )


@patch("app.render.get_audio_duration", return_value=1.0)  # <= ilk sahne -> 1 sahne
@patch("app.render.subprocess.run")
def test_render_video_single_scene_uses_simple_filtergraph(
    mock_run, mock_duration, tmp_path
):
    """Tek sahne: xfade zincirine düşmez; normalize+zoompan+subtitles."""
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip = tmp_path / "clip_0.mp4"
    clip.write_bytes(b"A")
    output_path = tmp_path / "final.mp4"

    stats: dict = {}
    result = render_video(
        [str(clip)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.ass"),
        str(output_path),
        str(tmp_path),
        stats_out=stats,
    )

    assert result == str(output_path)
    assert stats["scene_count"] == 1
    assert stats["clip_reuse_ratio"] == 1.0

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ffmpeg"

    # Tek video input + audio input; audio stream index = 1.
    assert cmd.count("-i") == 2
    joined = " ".join(cmd)
    assert "-map" in cmd
    assert "1:a:0" in cmd  # 1 video input -> audio 1:a:0
    assert "-filter_complex" in cmd
    # mp4 stock path: live Ken Burns (scale eval=frame), not freeze-frame zoompan
    assert "zoompan=" not in joined
    assert "eval=frame" in joined
    assert "xfade=" not in joined  # tek sahnede geçiş yok
    assert "subtitles=" in joined
    assert str(output_path) in cmd


@patch("app.render.get_audio_duration", return_value=30.0)
@patch("app.render.subprocess.run")
def test_render_video_derives_scene_count_from_audio_and_never_loops_raw(
    mock_run, mock_duration, tmp_path
):
    """Deterministik tavan: sahne sayısı ses süresinden gelir.

    ESKİ davranış [a,b,a,b,a,b,a] ham döngüsüydü (aynı kareler arka arkaya).
    YENİ davranış: 30 sn ses + 5.0 sn taban + 0.8 sn geçiş -> 10 sahne,
    ritim 1.6/1.6/1.6/5.../2.4 şeklinde değişken ve toplam tam 30.0 sn.
    """
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    clip_a.write_bytes(b"A")
    clip_b.write_bytes(b"B")
    output_path = tmp_path / "final.mp4"

    stats: dict = {}
    result = render_video(
        [str(clip_a), str(clip_b)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.ass"),
        str(output_path),
        str(tmp_path),
        stats_out=stats,
    )

    assert result == str(output_path)
    cmd = mock_run.call_args.args[0]
    joined = " ".join(cmd)

    # Sahne sayısı ses süresinden türetildi (sabit 6/10 değil).
    assert stats["scene_count"] == 10
    assert stats["clip_count"] == 2
    assert stats["clip_reuse_ratio"] == 5.0

    # 10 video input + 1 audio input.
    assert cmd.count("-i") == 11
    # Audio, 10 video input'tan sonra gelir -> stream index 10.
    assert "10:a:0" in cmd
    # concat demuxer kullanılmadı.
    assert "concat.txt" not in joined

    # Her input'ta normalize + live Ken Burns (mp4 → scale eval=frame, not zoompan).
    assert "zoompan=" not in joined
    assert joined.count("eval=frame") == 10
    assert joined.count("force_original_aspect_ratio=increase") == 10
    assert joined.count("crop=1080:1920") >= 10

    # Klip yetmediği için tekrar var, ama klipler ARKA ARKAYA gelmez ve
    # tekrar eden kullanım klibin farklı bir anından başlatılır.
    assert "-ss" in cmd

    # 10 sahne -> 9 geçiş; efektler tek tip değil, sırayla değişir.
    assert joined.count("xfade=transition=") == 9
    assert "xfade=transition=fade:" in joined
    assert "xfade=transition=circleopen:" in joined

    # Offset'ler kümülatif ve değişken ritme göre hesaplanır.
    for offset in ("0.8", "1.6", "2.4", "6.6", "10.8", "15.0", "19.2", "23.4", "27.6"):
        assert f"offset={offset}" in joined

    # Subtitles en son uygulanır; [vout] çıkışından sonra gelir.
    assert "subtitles=" in joined
    assert joined.index("xfade=") < joined.index("subtitles=")
    assert "[vfinal]" in joined


@patch("app.render.get_audio_duration", return_value=30.0)
@patch("app.render.subprocess.run")
def test_render_video_raises_on_ffmpeg_failure(mock_run, mock_duration, tmp_path):
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="encoder not found")
    clip = tmp_path / "clip_0.mp4"
    clip.write_bytes(b"A")

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        render_video(
            [str(clip)],
            str(tmp_path / "speech.mp3"),
            str(tmp_path / "subs.ass"),
            str(tmp_path / "out.mp4"),
            str(tmp_path),
        )


@patch("app.render.get_audio_duration", return_value=5.0)
@patch("app.render.subprocess.run")
def test_render_video_with_bgm_mixes_audio_streams(mock_run, mock_duration, tmp_path):
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip = tmp_path / "clip_0.mp4"
    clip.write_bytes(b"A")
    bgm = tmp_path / "music.mp3"
    bgm.write_bytes(b"BGM")
    output_path = tmp_path / "out.mp4"

    stats: dict = {}
    render_video(
        [str(clip)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.ass"),
        str(output_path),
        str(tmp_path),
        bgm_path=str(bgm),
        bgm_volume=0.12,
        stats_out=stats,
    )

    cmd = mock_run.call_args.args[0]
    joined = " ".join(cmd)
    assert "-i" in cmd
    # plan_scene_schedule(5.0) -> 4 sahne; 1 klip olduğu için 4 kez kullanılır.
    scenes = stats["scene_count"]
    assert scenes == 4
    assert cmd.count("-i") == scenes + 2  # sahne videoları + speech + bgm
    assert str(bgm) in cmd
    assert "amix=inputs=2" in joined
    assert "volume=0.12" in joined
    assert "-map [afinal]" in joined


@patch("app.render.get_audio_duration", return_value=4.0)
@patch("app.render.subprocess.run")
def test_render_video_without_zoompan_keeps_native_video_motion(
    mock_run, mock_duration, tmp_path
):
    """apply_zoompan=False olduğunda video kareleri dondurulmaz; zoompan filtresi kullanılmaz."""
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"DATA")
    output_path = tmp_path / "out.mp4"

    render_video(
        [str(clip)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.ass"),
        str(output_path),
        str(tmp_path),
        apply_zoompan=False,
    )

    cmd = mock_run.call_args.args[0]
    joined = " ".join(cmd)
    assert "zoompan=" not in joined
    assert "eval=frame" not in joined
    assert "fps=30" in joined
    assert "scale=1080:1920" in joined


@patch("app.render.get_audio_duration", return_value=4.0)
@patch("app.render.subprocess.run")
def test_render_stock_video_uses_live_kenburns_not_freeze_zoompan(
    mock_run, mock_duration, tmp_path
):
    """Stock mp4 + apply_zoompan → live scale/crop Ken Burns, never zoompan."""
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"DATA")

    render_video(
        [str(clip)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.ass"),
        str(tmp_path / "out.mp4"),
        str(tmp_path),
        apply_zoompan=True,
    )

    joined = " ".join(mock_run.call_args.args[0])
    assert "zoompan=" not in joined
    assert "eval=frame" in joined

