"""Yayın öncesi teknik kalite kapısı.

Yol haritası hedefi: "sessiz/bozuk video yayını = 0". Ölçüm (eklemeden önce):
`app/main.py` yayın öncesi videoyu hiç açmıyordu — yalnızca onay hash'ini
karşılaştırıyordu (`_verify_approved_artifact`). Yani diskte süresi 0, sesi
tamamen boş veya yarım yazılmış bir MP4, onaylandığı sürece yayınlanabiliyordu.
BGM regresyonu (sessiz video) üretim tarafında düzeltilmişti ama yayın öncesi
ikinci bir kontrol yoktu.

Bu modül bilinçli olarak "yumuşak" davranır: bir ölçüm alınamazsa (ffprobe yok,
bozuk konteyner, desteklenmeyen codec) karar `unknown` olur ve yayın bloklanmaz.
Sadece *ölçülmüş* bir ihlal engeller — yoksa video-worker'ın yayın yolu ffprobe
olmadan da çalışmaya devam etmeli.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Yayınlanabilir bir videonun alt sınırları. Kanal profili eklenirse buraya
# taşınmalı; tek bir "sihirli" değer varsaymıyoruz (bkz. yol haritası, Faz 3).
MIN_DURATION_SEC = 3.0
# -60 dB altındaki ortalama seviye pratikte sessiz demektir. Üretimde doğrudan
# etiketli `bgm_silence` durumu da kayda geçiyor; bu ikinci savunma hattı.
MIN_MEAN_VOLUME_DB = -60.0


@dataclass
class QualityVerdict:
    ok: bool
    reason: str = ""
    duration_sec: float | None = None
    has_audio_stream: bool | None = None
    mean_volume_db: float | None = None
    checks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "duration_sec": self.duration_sec,
            "has_audio_stream": self.has_audio_stream,
            "mean_volume_db": self.mean_volume_db,
            "checks": dict(self.checks),
        }


def _probe(path: Path) -> dict | None:
    """ffprobe JSON çıktısı; alınamazsa None (yayın bloklanmaz)."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            text=True,
            timeout=20,
            stderr=subprocess.DEVNULL,
        )
        return json.loads(out)
    except Exception:
        return None


def _mean_volume_db(path: Path) -> float | None:
    """`volumedetect` ile ortalama ses seviyesi; ölçülemezse None."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-v", "info",
                "-i", str(path),
                "-af", "volumedetect",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return None
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0].strip())
            except (IndexError, ValueError):
                return None
    return None



def evaluate(
    video_path: str | Path | None,
    *,
    bgm_silence: bool = False,
) -> QualityVerdict:
    """Yayın öncesi teknik kontrol.

    `bgm_silence`, üretim sırasında BGM bulunamadığını söyler. Bu tek başına
    ret nedeni değil: sentetik ambient fallback'i de sessiz olabilir, ama
    sesin *gerçekten* olup olmadığına dosyadan bakmak daha güvenilir. Bu
    yüzden ölçüm varsa ölçüm kazanır.
    """
    checks: dict[str, str] = {}
    path = Path(video_path) if video_path else None

    if path is None or not path.is_file():
        return QualityVerdict(
            ok=False, reason="video_missing", checks={"exists": "fail"}
        )
    checks["exists"] = "pass"

    probe = _probe(path)
    if probe is None:
        # Ölçemiyoruz: engellemiyoruz, ama görünür olsun.
        return QualityVerdict(
            ok=True,
            reason="probe_unavailable",
            checks={
                "probe": "unknown",
                "bgm_silence": "silent" if bgm_silence else "ok",
            },
        )
    checks["probe"] = "pass"

    duration: float | None = None
    try:
        duration = float((probe.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        duration = None

    streams = probe.get("streams") or []
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    checks["video_stream"] = "pass" if has_video else "fail"
    checks["audio_stream"] = "pass" if has_audio else "fail"

    if not has_video:
        return QualityVerdict(
            ok=False, reason="no_video_stream", duration_sec=duration,
            has_audio_stream=has_audio, checks=checks,
        )
    if duration is None or duration < MIN_DURATION_SEC:
        checks["duration"] = "fail"
        return QualityVerdict(
            ok=False, reason="too_short", duration_sec=duration,
            has_audio_stream=has_audio, checks=checks,
        )
    checks["duration"] = "pass"

    if not has_audio:
        # Ses akışı yoksa "sessiz video" — yol haritasının sıfırlamak istediği durum.
        return QualityVerdict(
            ok=False, reason="no_audio_stream", duration_sec=duration,
            has_audio_stream=False, checks=checks,
        )

    mean_db = _mean_volume_db(path)
    if mean_db is None:
        checks["volume"] = "unknown"
        return QualityVerdict(
            ok=True, reason="volume_unmeasurable", duration_sec=duration,
            has_audio_stream=True, checks=checks,
        )

    if mean_db < MIN_MEAN_VOLUME_DB:
        checks["volume"] = "fail"
        return QualityVerdict(
            ok=False, reason="audio_silent", duration_sec=duration,
            has_audio_stream=True, mean_volume_db=mean_db, checks=checks,
        )

    checks["volume"] = "pass"
    if bgm_silence:
        # Ölçüm ses olduğunu söylüyor (sentetik ambient veya konuşma). Yayını
        # durdurmuyoruz ama operatör görsün.
        checks["bgm_silence"] = "silent"
        return QualityVerdict(
            ok=True, reason="audio_present_bgm_missing", duration_sec=duration,
            has_audio_stream=True, mean_volume_db=mean_db, checks=checks,
        )

    return QualityVerdict(
        ok=True, duration_sec=duration, has_audio_stream=True,
        mean_volume_db=mean_db, checks=checks,
    )
