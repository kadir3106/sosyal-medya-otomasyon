"""Yayın sonucu belirsizken platforma "gerçekten yayınlandı mı?" diye sormak.

Yol haritası kuralı (Faz 4): *"Timeout sonrasında körlemesine yeniden yayın
yerine **önce durum sorgulama**."* Ölçüm (eklemeden önce): bu kural
uygulanamıyordu — hiçbir yayıncıda durum sorgulayan fonksiyon yoktu, yani
`status="unknown"` tek savunmaydı. Retry butonu sunmuyorduk ama işi kurtarmak
için de hiçbir şey yapamıyorduk: operatör platformu elle kontrol etmek zorundaydı.

Sorunun kökü zamanlama: yükleme sırasında üretilen platform kimliği
(`tiktok` → `publish_id`, `youtube` → `video_id`) *ancak* `upload_to_*`
döndüğünde elimize geçiyordu. Timeout tam o anda olduğu için kimlik kayıptı.

Çözüm iki parçalı:

1. `inflight` kaydı — yayıncı kimliği üretir üretmez diske yazılır, böylece
   thread takılsa bile çağıran taraf sorgulayabilir.
2. `PublishStatus` — platformdan bağımsız normalize durum. "Bilmiyorum" ile
   "yayınlandı" ayrımı operatör kararını belirlediği için bu ayrım korunur.

Yalnızca durumu *doğrulanabilen* platformlar destekleniyor. X, LinkedIn,
Pinterest, Instagram ve Facebook için yükleme anında hiçbir kimlik
bilinmiyor, dolayısıyla sorgu uydurmak yerine açıkça `unsupported` diyoruz.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.jsonstore import read_json, write_atomic

# Normalize durumlar. `unknown` bilinçli olarak `published`dan ayrı: ikisi aynı
# operatör kararını gerektirmiyor.
PUBLISHED = "published"
FAILED = "failed"
PENDING = "pending"     # platform hâlâ işliyor (yayınlanmış sayılmaz)
UNKNOWN = "unknown"     # sorgulanamadı (kimlik yok, ağ hatası, geçici belirsizlik)


@dataclass
class PublishStatus:
    platform: str
    state: str
    detail: str = ""
    url: str = ""

    @property
    def is_published(self) -> bool:
        return self.state == PUBLISHED

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "state": self.state,
            "detail": self.detail,
            "url": self.url,
        }


def _inflight_path(media_dir: str | Path, job_id: str) -> Path:
    return Path(media_dir) / "inflight" / f"{job_id}.json"


def record_inflight(
    media_dir: str | Path,
    job_id: str,
    platform: str,
    identity: dict,
) -> None:
    """Yayıncının ürettiği platform kimliğini, yükleme bitmeden kalıcılaştırır.

    Timeout anında tek kurtarma yolu bu kayıt: `upload_to_*` dönmediği için
    kimlik başka hiçbir yerde yok. Aynı iş+platform için yeniden yazılabilir
    (yayıncı kimliği yükleme başında üretiyor, sonunda değişmiyor).

    Erişim token'ı bilinçli olarak **yazılmıyor**: bu dosya `media/` altında
    düz JSON, token oraya sızarsa sır diskte kalır. Sorgu anında token canlı
    olarak yenileniyor.
    """
    safe = {k: v for k, v in (identity or {}).items() if k != "access_token"}
    if not safe:
        return
    payload = read_json(_inflight_path(media_dir, job_id), {})
    if not isinstance(payload, dict):
        payload = {}
    payload[platform] = safe
    write_atomic(_inflight_path(media_dir, job_id), payload)


def read_inflight(media_dir: str | Path, job_id: str) -> dict:
    payload = read_json(_inflight_path(media_dir, job_id), {})
    return payload if isinstance(payload, dict) else {}


def clear_inflight(media_dir: str | Path, job_id: str | None = None) -> None:
    """Sonuç kesinleşince kaydı sil. Kimliksiz iş için sessiz geçer."""
    if job_id is None:
        return
    _inflight_path(media_dir, job_id).unlink(missing_ok=True)


def query(media_dir: str | Path, job_id: str, platform: str) -> PublishStatus:
    """Tek platform için durumu sor; hiçbir zaman istisna fırlatmaz.

    Sorgu yapılamıyorsa `unknown` döner. Çağıran tarafın tek kararı var:
    `is_published` ise yeniden yayınlama.
    """
    from app.publishers import publication_status

    resolver = publication_status.RESOLVERS.get(platform)
    if resolver is None:
        return PublishStatus(
            platform, UNKNOWN, detail="no status API for this platform"
        )
    identity = read_inflight(media_dir, job_id).get(platform) or {}
    if not identity:
        # Kimlik yoksa yükleme muhtemelen hiç başlamadı ya da kimlik üretilmeden
        # düştü; bu durumda yayınlanmış olma ihtimali düşük ama *bilinmiyor*.
        return PublishStatus(platform, UNKNOWN, detail="no inflight identity")

    # Token kayıtta tutulmuyor (sır diskte kalmamalı); sorgu anında üretiliyor.
    credentials = _refresh_credentials(platform)
    if credentials is None:
        return PublishStatus(
            platform, UNKNOWN, detail="credentials unavailable for status query"
        )
    try:
        return resolver({**identity, **credentials})
    except Exception as exc:  # noqa: BLE001 - sorgu asla çağıranı düşürmemeli
        return PublishStatus(platform, UNKNOWN, detail=f"query failed: {exc}")


def _refresh_credentials(platform: str) -> dict | None:
    """Durum sorgusu için taze erişim token'ı; alınamazsa None.

    Hiçbir sır diske yazılmıyor: token her sorguda yenileniyor. Token
    yenilenemezse bu bir 'bilinmiyor' durumudur, 'yayınlanmadı' değil.
    """
    from app import config
    from app.publishers import publication_status

    refresher = publication_status.CREDENTIAL_REFRESHERS.get(platform)
    if refresher is None:
        return None
    try:
        return refresher(config)
    except Exception:
        return None


def query_all(media_dir: str | Path, job_id: str, platforms: list[str]) -> list[PublishStatus]:
    return [query(media_dir, job_id, p) for p in platforms]
