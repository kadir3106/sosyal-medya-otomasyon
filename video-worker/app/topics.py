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


def select_next_topic(
    topics_path: str,
    state_path: str,
    *,
    media_dir: str | None = None,
) -> str:
    """Havuzdan sıradaki konuyu seçer.

    `media_dir` verilirse konular **geçmiş performansa göre** sıralanır: daha
    çok izlenme almış konular öne alınır. Ölçüm (eklemeden önce): `topics.py`
    performansı hiç bilmiyordu, yani "yayın performansını konu seçimine geri
    besle" maddesi uygulanmıyordu.

    Sıralama bilinçli olarak **yumuşak**: kanıtlanmış yüksek performans öne
    geçer ama hiç ölçülmemiş konu da asla açlıkta kalmaz. Az örneklemle kesin
    hüküm vermemek için en az `MIN_SAMPLES_FOR_BOOST` video şartı aranıyor.
    """
    topics = json.loads(Path(topics_path).read_text(encoding="utf-8"))

    # Kilit şart: eşzamanlı çağrılar aksi hâlde aynı konuyu tekrar tekrar dağıtıyor
    # ve state dosyasını bozuyordu (ölçüm: 40 çağrıda 3 farklı konu, 30 tekrar).
    with locked_json(Path(state_path), {"used_topics": []}) as state:
        used = state.get("used_topics", [])
        remaining = [t for t in topics if t not in used]
        if not remaining:
            used = []
            remaining = topics

        next_topic = _rank_by_performance(remaining, media_dir)[0]
        used.append(next_topic)
        state["used_topics"] = used

    return next_topic


# Performans artışı için gereken en az video sayısı. Tek videonun şansı konu
# sıralamasını belirlememeli.
MIN_SAMPLES_FOR_BOOST = 2


def _rank_by_performance(topics: list[str], media_dir: str | None) -> list[str]:
    """Performansı kanıtlanmış konuları öne alır; sıralamayı bozmadan.

    Ölçüm yoksa (media_dir yok, defter boş, tüm örneklemler zayıf) giriş
    sırası korunur — mevcut davranış birebir aynı kalır.
    """
    if not media_dir or not topics:
        return list(topics)
    try:
        from app.performance_ledger import topic_performance

        stats = topic_performance(media_dir)
    except Exception:
        return list(topics)
    if not stats:
        return list(topics)

    def sort_key(indexed: tuple[int, str]) -> tuple[int, int]:
        index, topic = indexed
        bucket = stats.get(topic) or {}
        reliable = bucket.get("samples", 0) >= MIN_SAMPLES_FOR_BOOST
        # 0 = öne alınacaklar, 1 = geri kalanlar; grup içinde orijinal sıra korunur.
        return (0 if reliable else 1, index)

    ranked = [t for _, t in sorted(enumerate(topics), key=sort_key)]
    # Öne alınanlar kendi aralarında izlenmeye göre sıralanır.
    boosted = [t for t in ranked if (stats.get(t) or {}).get("samples", 0) >= MIN_SAMPLES_FOR_BOOST]
    boosted.sort(key=lambda t: stats[t].get("views", 0), reverse=True)
    rest = [t for t in ranked if t not in boosted]
    return boosted + rest


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
