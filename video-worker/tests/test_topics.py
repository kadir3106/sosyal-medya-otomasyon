import json
from app.topics import release_topic, resolve_en_topics_path, select_next_topic


def _write_topics(path, topics):
    path.write_text(json.dumps(topics), encoding="utf-8")


def test_selects_first_topic_when_state_empty(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B", "Topic C"])

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic A"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A"]


def test_skips_already_used_topics(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B", "Topic C"])
    state_path.write_text(json.dumps({"used_topics": ["Topic A"]}), encoding="utf-8")

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic B"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A", "Topic B"]


def test_resets_when_all_topics_used(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B"])
    state_path.write_text(
        json.dumps({"used_topics": ["Topic A", "Topic B"]}), encoding="utf-8"
    )

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic A"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A"]


def test_release_topic_returns_topic_to_pool(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B", "Topic C"])
    select_next_topic(str(topics_path), str(state_path))  # Topic A kullanıldı

    release_topic("Topic A", str(state_path))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == []
    # Havuzda baştan başlar → Topic A tekrar seçilir
    assert select_next_topic(str(topics_path), str(state_path)) == "Topic A"


def test_release_topic_noop_when_topic_not_used(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B"])
    select_next_topic(str(topics_path), str(state_path))  # Topic A kullanıldı

    release_topic("Topic B", str(state_path))  # kullanılmadı — değişiklik yok

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A"]


def test_release_topic_noop_when_no_state_file(tmp_path):
    release_topic("Topic A", str(tmp_path / "yok.json"))  # hata vermez


def test_resolve_en_topics_path_remaps_trivia_topics_json():
    assert resolve_en_topics_path("/app/data/topics.json").endswith(
        "topics_dark_wealth.json"
    )
    assert resolve_en_topics_path("/app/data/topics_dark_wealth.json").endswith(
        "topics_dark_wealth.json"
    )
    remapped = resolve_en_topics_path("/data/topics_trivia.json")
    assert remapped.endswith("topics_dark_wealth.json")


def test_concurrent_select_does_not_duplicate_topics(tmp_path):
    """Regression: unlocked read-modify-write handed out the same topic repeatedly.

    Measured before the fix: 40 concurrent calls returned only 3 distinct topics
    (30 duplicates) and 7 calls crashed with JSONDecodeError on the state file.
    Duplicated topics mean duplicated content, which YouTube flags as inauthentic.
    """
    import threading

    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "used_topics.json"
    topics = [f"topic-{i:03d}" for i in range(40)]
    topics_path.write_text(json.dumps(topics), encoding="utf-8")

    picked: list[str] = []
    guard = threading.Lock()

    def worker():
        t = select_next_topic(str(topics_path), str(state_path))
        with guard:
            picked.append(t)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(picked) == 40
    assert len(set(picked)) == 40, (
        f"duplicate topics handed out: {len(picked) - len(set(picked))}"
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert sorted(state["used_topics"]) == sorted(topics)

