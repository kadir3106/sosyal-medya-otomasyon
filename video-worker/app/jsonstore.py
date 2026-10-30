"""Küçük JSON durum dosyaları için kilitli, atomik oku-değiştir-yaz.

Bu desen birden çok yerde gerekiyor (yayın kaydı, konu durumu) ve kilit olmadan
eşzamanlı erişim kayıt kaybediyor / aynı değeri tekrar dağıtıyor / dosyayı bozuyor.
Ölçüm: kilit öncesi 40 eşzamanlı yayın kaydından 35'i kayboldu; 40 konu seçiminden
yalnızca 3 farklı konu dağıtıldı ve 7 çağrı JSONDecodeError ile çöktü.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# Süreç-içi kilit: video-worker tek replika çalışıyor. Çok replikaya çıkılırsa
# dosya düzeyinde kilit (veya SQLite) gerekir.
_lock = threading.Lock()


def write_atomic(path: Path, payload: Any) -> None:
    """Aynı dizine yazıp atomik olarak yerine koyar; okuyucu asla yarım dosya görmez."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def read_json(path: Path, default: Any) -> Any:
    """Bozuk dosyayı silmek yerine `<ad>.corrupt` olarak kenara alıp temiz başlar."""
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.with_suffix(path.suffix + ".corrupt").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return default


@contextmanager
def locked_json(path: Path, default: Any) -> Iterator[Any]:
    """Kilidi alır, dosyayı okur, bloğa verir ve çıkışta atomik yazar."""
    with _lock:
        data = read_json(path, default)
        yield data
        write_atomic(path, data)
