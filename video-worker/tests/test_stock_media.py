from unittest.mock import patch, Mock

from app.stock_media import (
    extract_keywords,
    fetch_stock_clips,
    _generate_fallback_clips,
    _load_used_clip_ids,
    _render_fallback_frame,
    _save_used_clip_ids,
    _search_portrait_video,
)


def test_extract_keywords_filters_stopwords_and_short_words():
    script = "The flamingo stands on one leg to conserve body heat in cold water"
    keywords = extract_keywords(script, max_keywords=3)
    assert keywords == ["flamingo", "stands", "conserve"]


def test_extract_keywords_falls_back_to_nature_when_empty():
    assert extract_keywords("a to of in on", max_keywords=3) == ["nature"]


def test_extract_keywords_supports_turkish_chars():
    keywords = extract_keywords("Zürafaların ses telleri yokmuş", max_keywords=3)
    assert keywords == ["zürafaların", "telleri", "yokmuş"]


def _search_response(link):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "videos": [
            {
                "video_files": [
                    {"link": "https://example.com/landscape.mp4", "width": 1920, "height": 1080},
                    {"link": link, "width": 1080, "height": 1920},
                ]
            }
        ]
    }
    return resp


def _download_response(content):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.content = content
    return resp


@patch("app.stock_media.session.get")
def test_fetch_stock_clips_downloads_portrait_file(mock_get, tmp_path):
    mock_get.side_effect = [
        _search_response("https://example.com/portrait.mp4"),
        _download_response(b"FAKEVIDEOBYTES"),
    ]

    result = fetch_stock_clips(
        ["flamingo"], count=1, api_key="fake-key", output_dir=str(tmp_path)
    )

    assert result == [str(tmp_path / "clip_0.mp4")]
    assert (tmp_path / "clip_0.mp4").read_bytes() == b"FAKEVIDEOBYTES"
    search_call = mock_get.call_args_list[0]
    assert search_call.kwargs["headers"]["Authorization"] == "fake-key"
    assert search_call.kwargs["params"]["query"] == "flamingo"
    # per_page=1 hep aynı klibi döndürüyordu — daha geniş bir havuzdan
    # rastgele seçebilmek için per_page yükseltildi (bkz. K7).
    assert search_call.kwargs["params"]["per_page"] == 15


@patch("app.stock_media.session.get")
def test_fetch_stock_clips_cycles_through_keywords(mock_get, tmp_path):
    mock_get.side_effect = [
        _search_response("https://example.com/a.mp4"),
        _download_response(b"A"),
        _search_response("https://example.com/b.mp4"),
        _download_response(b"B"),
    ]

    result = fetch_stock_clips(
        ["flamingo", "wetland"], count=2, api_key="fake-key", output_dir=str(tmp_path)
    )

    assert len(result) == 2
    queries = [
        c.kwargs["params"]["query"]
        for c in mock_get.call_args_list
        if "params" in c.kwargs
    ]
    assert queries == ["flamingo", "wetland"]


def test_fetch_stock_clips_uses_fallback_when_no_api_key(tmp_path):
    with patch("app.stock_media._generate_fallback_clips") as mock_fallback:
        mock_fallback.return_value = [str(tmp_path / "fallback_0.mp4")]

        result = fetch_stock_clips(
            ["flamingo"], count=2, api_key="", output_dir=str(tmp_path)
        )

    assert result == [str(tmp_path / "fallback_0.mp4")]
    mock_fallback.assert_called_once_with(2, str(tmp_path))


@patch("app.stock_media._generate_fallback_clips")
@patch("app.stock_media._search_portrait_video", return_value=(None, None))
def test_fetch_stock_clips_falls_back_when_pexels_empty(
    mock_search, mock_fallback, tmp_path
):
    mock_fallback.return_value = [str(tmp_path / "fallback_0.mp4")]

    result = fetch_stock_clips(
        ["flamingo"], count=2, api_key="fake-key", output_dir=str(tmp_path)
    )

    assert result == [str(tmp_path / "fallback_0.mp4")]
    mock_fallback.assert_called_once_with(2, str(tmp_path))


@patch("app.stock_media.subprocess.run")
def test_generate_fallback_clips_creates_clips(mock_run, tmp_path):
    mock_run.return_value.returncode = 0

    clips = _generate_fallback_clips(
        count=2,
        output_dir=str(tmp_path),
        accent="#38BDF8",
        size=(54, 96),
        fps=1,
        duration=1,
    )

    assert clips == [str(tmp_path / "fallback_0.mp4"), str(tmp_path / "fallback_1.mp4")]
    assert mock_run.call_count == 2
    # kare klasörleri encode sonrası temizlenmeli
    assert not (tmp_path / "fallback_frames_0").exists()


def test_render_fallback_frame_produces_expected_size():
    image = _render_fallback_frame(
        frame_index=3,
        frame_count=10,
        clip_index=0,
        clip_count=2,
        accent="#38BDF8",
        size=(54, 96),
    )
    assert image.size == (54, 96)
    assert image.mode == "RGB"


def _multi_video_response(videos):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"videos": videos}
    return resp


def _portrait_video(video_id, link):
    return {
        "id": video_id,
        "video_files": [{"link": link, "width": 1080, "height": 1920}],
    }


def test_used_clip_ids_round_trip(tmp_path):
    state_path = str(tmp_path / "used_clips.json")

    assert _load_used_clip_ids(state_path) == set()

    _save_used_clip_ids(state_path, {1, 2, 3})

    assert _load_used_clip_ids(state_path) == {1, 2, 3}


def test_save_used_clip_ids_trims_to_history_limit(tmp_path):
    state_path = str(tmp_path / "used_clips.json")

    _save_used_clip_ids(state_path, set(range(500)))

    assert len(_load_used_clip_ids(state_path)) == 200


@patch("app.stock_media.session.get")
def test_search_portrait_video_excludes_already_used_ids(mock_get):
    mock_get.return_value = _multi_video_response([
        _portrait_video(1, "https://example.com/used.mp4"),
        _portrait_video(2, "https://example.com/fresh.mp4"),
    ])

    video_id, link = _search_portrait_video("nature", "fake-key", exclude_ids={1})

    assert video_id == 2
    assert link == "https://example.com/fresh.mp4"


@patch("app.stock_media.session.get")
def test_search_portrait_video_falls_back_to_full_pool_when_all_excluded(mock_get):
    mock_get.return_value = _multi_video_response([
        _portrait_video(1, "https://example.com/a.mp4"),
    ])

    # Havuzdaki tek video da hariç tutulan listede — yine de bir sonuç dönmeli,
    # üretim tekrar riski yüzünden asla durmamalı.
    video_id, link = _search_portrait_video("nature", "fake-key", exclude_ids={1})

    assert video_id == 1
    assert link == "https://example.com/a.mp4"


@patch("app.stock_media.session.get")
def test_fetch_stock_clips_persists_newly_used_ids(mock_get, tmp_path):
    state_path = str(tmp_path / "used_clips.json")
    mock_get.side_effect = [
        _multi_video_response([_portrait_video(42, "https://example.com/x.mp4")]),
        Mock(raise_for_status=Mock(), content=b"BYTES"),
    ]

    fetch_stock_clips(
        ["flamingo"], count=1, api_key="fake-key",
        output_dir=str(tmp_path), state_path=state_path,
    )

    assert _load_used_clip_ids(state_path) == {42}
