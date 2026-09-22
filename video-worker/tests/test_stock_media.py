from unittest.mock import patch, Mock
import re

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
            ["flamingo"],
            count=2,
            api_key="",
            output_dir=str(tmp_path),
            enable_mixkit=False,
            pixabay_api_key="",
        )

    assert result == [str(tmp_path / "fallback_0.mp4")]
    mock_fallback.assert_called_once_with(2, str(tmp_path))


@patch("app.stock_media._generate_fallback_clips")
@patch("app.stock_media._search_stock_waterfall", return_value=None)
def test_fetch_stock_clips_falls_back_when_pexels_empty(
    mock_search, mock_fallback, tmp_path
):
    mock_fallback.return_value = [str(tmp_path / "fallback_0.mp4")]

    result = fetch_stock_clips(
        ["flamingo"],
        count=2,
        api_key="fake-key",
        output_dir=str(tmp_path),
        enable_mixkit=False,
    )

    assert result == [str(tmp_path / "fallback_0.mp4")]
    mock_fallback.assert_called_once_with(2, str(tmp_path))
    assert mock_search.called


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


def _portrait_video(video_id, link, url=None):
    return {
        "id": video_id,
        "url": url or f"https://www.pexels.com/video/clip-{video_id}/",
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

    video_id, link, reused = _search_portrait_video("nature", "fake-key", exclude_ids={1})

    assert video_id == 2
    assert link == "https://example.com/fresh.mp4"
    assert reused is False


@patch("app.stock_media.session.get")
def test_search_portrait_video_refuses_used_ids_by_default(mock_get):
    mock_get.return_value = _multi_video_response([
        _portrait_video(1, "https://example.com/a.mp4"),
    ])

    # Havuzdaki tek video hariç tutulan listede — sessiz reuse YOK (konu drift).
    video_id, link, reused = _search_portrait_video("nature", "fake-key", exclude_ids={1})

    assert video_id is None
    assert link is None
    assert reused is False


@patch("app.stock_media.session.get")
def test_search_portrait_video_allows_used_id_reuse_when_opted_in(mock_get):
    mock_get.return_value = _multi_video_response([
        _portrait_video(1, "https://example.com/a.mp4"),
    ])

    video_id, link, reused = _search_portrait_video(
        "nature", "fake-key", exclude_ids={1}, allow_used_id_reuse=True
    )

    assert video_id == 1
    assert link == "https://example.com/a.mp4"
    assert reused is True


def test_topic_anchor_keeps_de_beers_intact():
    from app.stock_media import topic_anchor_terms, enrich_stock_query

    anchors = topic_anchor_terms(
        "The De Beers Diamond Scam: How an advertising cartel convinced the world"
    )
    assert any(a.lower() == "de beers" for a in anchors)
    assert "Beers" not in anchors  # orphan second half alone is wrong

    q = enrich_stock_query(
        "Beers diamond ring jewelry",
        topic="The De Beers Diamond Scam",
        mode="diamond",
    )
    low = q.lower()
    assert "de beers" in low
    assert not re.search(r"(?<!de )\bbeers\b", low)


def test_build_scene_search_query_anchors_to_topic_not_generic_wealth():
    from app.stock_media import build_scene_search_query

    q = build_scene_search_query(
        "Rolex Swiss trust / dark wealth",
        prompt="cinematic dramatic photorealistic 8k luxury lifestyle dolly",
        keyword_hint="luxury",
        scene_index=0,
    )
    low = q.lower()
    assert "rolex" in low or "swiss" in low
    assert low != "luxury business"
    assert "luxury lifestyle" not in low


def test_resolve_de_beers_scene_not_orphan_beers():
    from app.stock_media import resolve_scene_queries

    queries = resolve_scene_queries(
        scene_count=1,
        topic="The De Beers Diamond Scam: How an advertising cartel...",
        script="Your engagement ring is worth zero after you leave the store.",
        scene_stock_queries=[
            {"query": "engagement ring price tag jewelry counter", "mode": "diamond"}
        ],
    )
    assert "de beers" in queries[0].lower() or "engagement" in queries[0].lower()
    assert not re.search(r"(?<!de )\bbeers\b", queries[0].lower())


def test_build_scene_search_query_prefers_rich_scene_query():
    from app.stock_media import build_scene_search_query

    q = build_scene_search_query(
        "Rolex Swiss trust",
        prompt="ignored fluff",
        scene_query="swiss bank vault legal documents corporate trust papers",
        mode="finance_docs",
    )
    low = q.lower()
    assert "vault" in low or "document" in low or "legal" in low
    assert "construction" not in low


def test_resolve_scene_queries_uses_llm_scene_stock_queries():
    from app.stock_media import resolve_scene_queries

    queries = resolve_scene_queries(
        scene_count=2,
        topic="Rolex Foundation Swiss trust",
        script="Rolex is a tax-free Swiss trust. Watchmakers build every crown.",
        scene_stock_queries=[
            {"query": "swiss bank vault legal contract papers", "mode": "finance_docs"},
            {"query": "luxury watchmaker loupe mechanical gears", "mode": "watchmaking"},
        ],
    )
    assert len(queries) == 2
    assert "vault" in queries[0].lower() or "legal" in queries[0].lower() or "contract" in queries[0].lower()
    assert "watch" in queries[1].lower() or "gear" in queries[1].lower() or "loupe" in queries[1].lower()


def test_detect_visual_mode_finance_and_watch():
    from app.stock_media import detect_visual_mode

    assert detect_visual_mode("tax-free Swiss trust shareholders") in (
        "finance_docs",
        "vault",
        "chart",
    )
    assert detect_visual_mode("Rolex watchmaker gears mechanism") == "watchmaking"


def test_score_rejects_construction_slug_for_watch_query():
    from app.stock_media import _score_stock_candidate

    assert _score_stock_candidate(
        "https://www.pexels.com/video/construction-site-excavator-123/",
        "luxury watchmaker gears",
    ) < 0


def test_build_scene_search_query_rotates_topic_anchors_across_scenes():
    from app.stock_media import build_scene_search_query

    topic = "Rolex Swiss vault Geneva"
    q0 = build_scene_search_query(
        topic, prompt="swiss vault steel door", scene_index=0, mode="vault"
    )
    q1 = build_scene_search_query(
        topic, prompt="geneva watchmaker bench tools", scene_index=1, mode="watchmaking"
    )
    # Different scene prompts must not collapse to the identical query string.
    assert q0 != q1


@patch("app.stock_media.session.get")
def test_fetch_stock_clips_persists_newly_used_ids(mock_get, tmp_path):
    state_path = str(tmp_path / "used_clips.json")
    mock_get.side_effect = [
        _multi_video_response([_portrait_video(42, "https://example.com/x.mp4")]),
        Mock(raise_for_status=Mock(), content=b"BYTES"),
    ]

    fetch_stock_clips(
        ["flamingo"],
        count=1,
        api_key="fake-key",
        output_dir=str(tmp_path),
        state_path=state_path,
        enable_mixkit=False,
    )

    assert _load_used_clip_ids(state_path) == {"pexels:42"}


@patch("app.stock_media._download_file")
@patch("app.stock_media._search_portrait_video", return_value=(None, None, False))
@patch("app.stock_media._search_pixabay_video")
def test_fetch_stock_clips_falls_through_to_pixabay(
    mock_pixabay, mock_pexels, mock_download, tmp_path
):
    mock_pixabay.return_value = (99, "https://example.com/pixabay.mp4", False)
    meta = {}

    result = fetch_stock_clips(
        ["rolex watch"],
        count=1,
        api_key="pexels-key",
        pixabay_api_key="pixabay-key",
        enable_mixkit=False,
        output_dir=str(tmp_path),
        meta_out=meta,
        fallback_on_empty=False,
    )

    assert result == [str(tmp_path / "clip_0.mp4")]
    assert meta["providers"] == ["pixabay"]
    assert meta["scene_relevance"][0]["source"] == "pixabay"
    mock_download.assert_called_once()


@patch("app.stock_media.session.get")
def test_search_pixabay_video_picks_tallest_variant(mock_get):
    from app.stock_media import _search_pixabay_video

    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "hits": [
            {
                "id": 7,
                "videos": {
                    "large": {"url": "https://cdn.example/large.mp4", "width": 1920, "height": 1080},
                    "medium": {"url": "https://cdn.example/med.mp4", "width": 720, "height": 1280},
                    "small": {"url": "https://cdn.example/small.mp4", "width": 480, "height": 640},
                },
            }
        ]
    }
    mock_get.return_value = resp

    vid, url, reused = _search_pixabay_video("swiss watch", "key")
    assert vid == 7
    assert url == "https://cdn.example/med.mp4"
    assert reused is False


@patch("app.stock_media.session.get")
def test_search_mixkit_video_extracts_mp4_urls(mock_get):
    from app.stock_media import _search_mixkit_video

    resp = Mock()
    resp.status_code = 200
    resp.raise_for_status = Mock()
    resp.text = (
        '<html><video src="https://assets.mixkit.co/videos/preview/mixkit-clock-123.mp4">'
        "</video></html>"
    )
    mock_get.return_value = resp

    vid, url, reused = _search_mixkit_video("swiss clock")
    assert vid == "mixkit-clock-123"
    assert url.endswith("mixkit-clock-123.mp4")
    assert reused is False

