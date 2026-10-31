"""Yayın performansının kalıcı defteri — geri besleme döngüsünün eksik yarısı.

Ölçüm (eklemeden önce): döngü **açıktı**.

| Parça | Durum |
|---|---|
| `analytics_memory.format_hook_memory_context` pipeline'da okunuyor | ✅ |
| `store_winning_hook` çağıran | **0** |
| `analytics.py` içinde diske yazma | **YOK** (rapor her seferinde yeniden çekiliyor) |
| `topics.py` içinde performans sinyali | **YOK** |

Somut sonuç: `winning_hooks.json` hiç yazılmadığı için prompt eki her zaman 0
karakterdi; hafıza hiç konuşmuyordu. Elle yazıldığında 203 karaktere çıkıyor,
yani okuma tarafı sağlamdı — yazan yoktu.

Bu modül ölçülen değerleri saklar. Haftalık rapor artık platformdan gelen
sayıları atıp yeniden çekmek yerine buradan okuyor, ve `topics.py` konu
havuzunu geçmiş performansa göre sıralayabiliyor.

Tasarım kararı: defter **append-only**, kayıt `<job_id>:<platform>` anahtarıyla
tekilleştirilir. Aynı video için her hafta yeni ölçüm gelmesi normaldir ama
aynı hafta iki kez rapor çekmek mükerrer satır üretmemeli.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.jsonstore import locked_json, read_json

LEDGER_NAME = "performance_ledger.json"


def _path(media_dir: str | Path) -> Path:
    return Path(media_dir) / LEDGER_NAME


def _key(entry: dict[str, Any]) -> str:
    return f"{entry.get('job_id') or '?'}:{entry.get('platform') or '?'}"


def record_metrics(
    media_dir: str | Path,
    *,
    job_id: str,
    topic: str = "",
    title: str = "",
    hook: str = "",
    platform: str,
    metrics: dict[str, Any],
    captured_at: str | None = None,
) -> None:
    """Bir platformun ölçülen metriklerini deftere ekler (aynı anahtarı tazeler).

    `metrics` ham hâliyle saklanır: platformlar arasında "izlenme" aynı şeyi
    ifade etmiyor (bkz. yol haritası Faz 4: "ham metrik saklanmalı"). Normalize
    etmek çağıranın işi.
    """
    if not job_id or not platform:
        return
    entry = {
        "job_id": job_id,
        "platform": platform,
        "topic": topic,
        "title": title,
        "hook": hook,
        "metrics": dict(metrics or {}),
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
    }
    with locked_json(_path(media_dir), []) as entries:
        if not isinstance(entries, list):
            entries.clear()
        entries[:] = [e for e in entries if isinstance(e, dict) and _key(e) != _key(entry)]
        entries.append(entry)


def load_metrics(
    media_dir: str | Path,
    *,
    since_iso: str | None = None,
) -> list[dict[str, Any]]:
    data = read_json(_path(media_dir), [])
    if not isinstance(data, list):
        return []
    rows = [e for e in data if isinstance(e, dict)]
    if since_iso:
        rows = [e for e in rows if str(e.get("captured_at") or "") >= since_iso]
    return rows


def _views(entry: dict[str, Any]) -> int:
    """Ham metrikten izlenme sayısını çıkarır; yoksa 0.

    Bilinçli olarak tek alan: farklı platformların "izlenme" tanımı farklı ve
    yanlış normalize etmek karşılaştırmayı bozar. Sıralama için kaba bir sinyal
    yeterli, kesin bir hüküm değil.
    """
    metrics = entry.get("metrics") or {}
    for field in ("views", "plays", "view_count"):
        raw = metrics.get(field)
        if raw is None:
            continue
        try:
            return int(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return 0


def topic_performance(media_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Konu bazında toplam izlenme ve video sayısı.

    Aynı konu birden çok videoda kullanılabilir; birikimli toplam anlamlı bir
    sinyaldir ama örneklem küçükken kesin hüküm değildir. Bu yüzden
    `samples` alanı da dönüyor.
    """
    summary: dict[str, dict[str, Any]] = {}
    for entry in load_metrics(media_dir):
        topic = (entry.get("topic") or "").strip()
        if not topic:
            continue
        bucket = summary.setdefault(topic, {"views": 0, "samples": 0})
        bucket["views"] += _views(entry)
        bucket["samples"] += 1
    for bucket in summary.values():
        bucket["avg_views"] = (
            round(bucket["views"] / bucket["samples"], 1) if bucket["samples"] else 0.0
        )
    return summary


def best_hooks(media_dir: str | Path, *, limit: int = 5) -> list[dict[str, Any]]:
    """En çok izlenen hook'lar — `analytics_memory`'nin beklediği biçimde.

    `analytics_memory.format_hook_memory_context` bu kayıtları okuyup prompt'a
    "şu açılışları tekrar etme" talimatı olarak ekliyor; döngü burada kapanıyor.
    """
    by_hook: dict[str, dict[str, Any]] = {}
    for entry in load_metrics(media_dir):
        hook = (entry.get("hook") or "").strip()
        if not hook:
            continue
        bucket = by_hook.setdefault(
            hook, {"hook": hook, "views": 0, "samples": 0, "topic": entry.get("topic", "")}
        )
        bucket["views"] += _views(entry)
        bucket["samples"] += 1
    ranked = sorted(by_hook.values(), key=lambda b: b["views"], reverse=True)
    return ranked[:limit]
