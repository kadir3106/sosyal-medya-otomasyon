import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.catchup import mark_run_today, ran_today
from app.telegram_bot import send_message

DIGEST_MARKER_FILENAME = "digest_sent.txt"

# Günlük özet, "bugün yayınlanan içerik"i Europe/Istanbul gün sınırıyla hesaplar.
# published_at UTC ISO biçiminde saklanır (bkz. main.py _run_publish); karşılaştırma
# için bugünün yerel başlangıcını UTC ISO'ya çeviririz.
try:
    from zoneinfo import ZoneInfo

    _ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover - zoneinfo yoksa UTC'ye düş (sadece filtreleme kayar)
    _ISTANBUL_TZ = None


def _local_today_start_utc(now: datetime) -> str:
    """Europe/Istanbul'da 'bugün'ün başlangıcını UTC ISO olarak döndürür."""
    if _ISTANBUL_TZ is not None and now.tzinfo is not None:
        local_now = now.astimezone(_ISTANBUL_TZ)
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight.astimezone(now.tzinfo).isoformat()
    # Naive now (testler): UTC gün başlangıcıyla filtrele — testler yazarken now UTC verilir.
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def build_daily_digest(media_dir: str, now: Optional[datetime] = None) -> str:
    """Gün sonu özet mesajını kurar.

    Kaynaklar:
      - published_log.json  → bugün yayınlanan içerikler (platform bazında sonuç)
      - pending.json        → varsa, onay bekleyen iş hatırlatması
    """
    now = now or datetime.now()
    since_iso = _local_today_start_utc(now)
    media = Path(media_dir)

    entries = []
    log_path = media / "published_log.json"
    if log_path.is_file():
        try:
            all_entries = json.loads(log_path.read_text(encoding="utf-8"))
            entries = [e for e in all_entries if e.get("published_at", "") >= since_iso]
        except (json.JSONDecodeError, OSError):
            entries = []

    lines = ["📋 Günlük Özet", ""]
    if entries:
        lines.append(f"Bugün {len(entries)} içerik yayınlandı:")
        for entry in entries:
            kind = entry.get("kind", "video")
            icon = "🖼" if kind == "image" else "🎬"
            title = entry.get("title") or "(başlıksız)"
            lines.append(f"{icon} {title}")
            platforms = entry.get("platforms", {})
            for name, result in platforms.items():
                if result.get("status") == "success":
                    lines.append(f"   ✅ {name}")
                else:
                    err = result.get("error") or "hata"
                    lines.append(f"   ❌ {name}: {err}")
        lines.append("")
    else:
        lines.append("Bugün yeni bir içerik yayınlanmadı.")
        lines.append("")

    pending_path = media / "pending.json"
    if pending_path.is_file():
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            p_title = pending.get("title") or pending.get("caption") or "(başlıksız)"
            p_kind = "🖼 görsel" if pending.get("kind") == "image" else "🎬 video"
            lines.append(f"⏳ Onay bekleyen {p_kind}: {p_title}")
            lines.append("Lütfen Telegram'daki onay/red butonuyla karar ver.")
        except (json.JSONDecodeError, OSError):
            pass
    else:
        lines.append("Bekleyen onay yok.")

    return "\n".join(lines)


def maybe_send_digest(
    token: str,
    chat_id: str,
    media_dir: str,
    digest_hour: int,
    marker_path: str,
    now: Optional[datetime] = None,
    send_fn=None,
) -> bool:
    """Günlük özeti vaktinde (digest_hour geçtiyse) ve günde bir kez gönderir.

    `now` verilmezse sistem saati kullanılır (container TZ=Europe/Istanbul).
    Gönderildiyse True döner.
    """
    now = now or datetime.now()
    if now.hour < digest_hour:
        return False
    if ran_today(marker_path, today=now.date()):
        return False

    sender = send_fn or send_message
    message = build_daily_digest(media_dir, now=now)
    sender(token, chat_id, message)
    mark_run_today(marker_path, today=now.date())
    return True


async def run_digest_loop(
    token: str,
    chat_id: str,
    media_dir: str,
    digest_hour: int,
    marker_path: str,
    interval_seconds: int = 300,
) -> None:
    """Periyodik olarak günlük özetin vaktinin gelip gelmediğini kontrol eder."""
    print(f"[daily_digest] Günlük özet dinleyici başladı (saat {digest_hour}:00).", flush=True)
    while True:
        try:
            sent = await asyncio.to_thread(
                maybe_send_digest, token, chat_id, media_dir, digest_hour, marker_path
            )
            if sent:
                print("[daily_digest] Günlük özet gönderildi.", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[daily_digest] Özet gönderme hatası: {exc}", flush=True)
        await asyncio.sleep(interval_seconds)
