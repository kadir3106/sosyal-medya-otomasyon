from datetime import date, datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

VIDEO_MARKER_FILENAME = "last_video_run.txt"
IMAGE_MARKER_FILENAME = "last_image_run.txt"


def mark_run_today(marker_path: str, today: date = None) -> None:
    Path(marker_path).write_text((today or date.today()).isoformat(), encoding="utf-8")


def ran_today(marker_path: str, today: date = None) -> bool:
    path = Path(marker_path)
    if not path.is_file():
        return False
    return path.read_text(encoding="utf-8").strip() == (today or date.today()).isoformat()


def past_scheduled_hour(scheduled_hour: int, now: datetime = None) -> bool:
    return (now or datetime.now()).hour >= scheduled_hour


async def maybe_catch_up(
    media_dir: str,
    video_hour: int,
    image_hour: int,
    generate_video_fn: Callable[[], Awaitable[object]],
    generate_image_fn: Callable[[], Awaitable[object]],
    now: datetime = None,
) -> Optional[str]:
    """PC/container kapalıyken atlanan günlük bir işi (video veya görsel) yakalar.

    n8n'in cron'u yalnızca tam zamanında ateşler — o an sistem kapalıysa o günün
    işi sessizce hiç olmaz. Bu fonksiyon uygulama açılışında çağrılır: bugün
    henüz çalışmamış ve zamanlanan saati geçmiş bir iş varsa şimdi tetikler.
    Video, görselden önceliklidir (aynı anda ikisi birden tetiklenmez — bekleyen
    onay tek seferde tek iş kabul ediyor, bkz. /generate ve /generate-image).

    Zaten bekleyen bir onay varsa (pending.json) hiçbir şey yapmaz — üstüne
    yenisini üretmez. "Bugün çalıştı" işareti, marker dosyasını yazan asıl
    /generate ve /generate-image endpoint'lerinin sorumluluğunda (tek bir yerden
    işaretlenir, hem normal cron çağrısı hem bu yakalama aynı mekanizmayı kullanır).

    Döndürdüğü değer yalnızca loglama/bilgi amaçlıdır: "video", "image" ya da
    hiçbir şey tetiklenmediyse None.
    """
    if (Path(media_dir) / "pending.json").is_file():
        return None

    current = now or datetime.now()

    video_marker = str(Path(media_dir) / VIDEO_MARKER_FILENAME)
    if not ran_today(video_marker, today=current.date()) and past_scheduled_hour(video_hour, current):
        await generate_video_fn()
        return "video"

    image_marker = str(Path(media_dir) / IMAGE_MARKER_FILENAME)
    if not ran_today(image_marker, today=current.date()) and past_scheduled_hour(image_hour, current):
        await generate_image_fn()
        return "image"

    return None
