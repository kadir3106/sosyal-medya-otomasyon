import json
import logging
from pathlib import Path

from app.jsonstore import locked_json

logger = logging.getLogger(__name__)

# EN daily niche lock — never silently serve trivia pools (space/ants/etc.).
DARK_WEALTH_BASENAME = "topics_dark_wealth.json"
TRIVIA_BASENAMES = frozenset(
    {
        "topics.json",
        "video_topics.json",
        "trivia.json",
        "topics_trivia.json",
    }
)


def resolve_en_topics_path(topics_path: str) -> str:
    """Map trivia / legacy EN pools to topics_dark_wealth.json; keep dark wealth as-is."""
    raw = (topics_path or "").strip() or f"/app/data/{DARK_WEALTH_BASENAME}"
    path = Path(raw)
    name = path.name.lower()
    if name == DARK_WEALTH_BASENAME:
        return raw
    if name in TRIVIA_BASENAMES or "trivia" in name:
        remapped = str(path.with_name(DARK_WEALTH_BASENAME))
        logger.warning(
            "TOPICS_PATH trivia/legacy pool refused (%s) → remapped to %s",
            raw,
            remapped,
        )
        return remapped
    return raw


def select_next_topic(topics_path: str, state_path: str) -> str:
    topics = json.loads(Path(topics_path).read_text(encoding="utf-8"))

    # Kilit şart: eşzamanlı çağrılar aksi hâlde aynı konuyu tekrar tekrar dağıtıyor
    # ve state dosyasını bozuyordu (ölçüm: 40 çağrıda 3 farklı konu, 30 tekrar).
    with locked_json(Path(state_path), {"used_topics": []}) as state:
        used = state.get("used_topics", [])
        remaining = [t for t in topics if t not in used]
        if not remaining:
            used = []
            remaining = topics

        next_topic = remaining[0]
        used.append(next_topic)
        state["used_topics"] = used

    return next_topic


def release_topic(topic: str, state_path: str) -> None:
    """Üretim başarısız olursa konuyu havuza geri bırakır (ertesi gün yeniden denenebilir)."""
    state_file = Path(state_path)
    if not state_file.exists():
        return

    with locked_json(state_file, {"used_topics": []}) as state:
        used = state.get("used_topics", [])
        if topic not in used:
            return
        used.remove(topic)
        state["used_topics"] = used
