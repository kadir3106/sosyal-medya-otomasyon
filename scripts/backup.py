#!/usr/bin/env python3
"""n8n workflow/credential verisini ve yayın geçmişini yerel bir arşive yedekler.

Neyi yedekler:
  - n8n-data volume'ü (workflow'lar, credential'lar, SQLite veritabanı)
  - shared-media volume'ünden: used_topics.json, used_image_topics.json,
    published_log.json (üretilen video/görsel dosyaları DEĞİL — onlar zaten
    yayınlandıktan sonra siliniyor, yedeklenecek kalıcı veri değil)

Kullanım:
    python scripts/backup.py

Çıktı: backups/otomasyon-yedek-YYYY-MM-DD.tar.gz (proje kökünde, .gitignore'da)
"""

import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "backups"
MEDIA_FILES = ["used_topics.json", "used_image_topics.json", "published_log.json"]


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"HATA: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(1)


def find_n8n_volume() -> str:
    # Docker Compose volume adını proje dizin adına göre öneklendiriyor
    # (örn. "sosyal-medya-otomasyon_n8n-data") — dizin taşınırsa/yeniden
    # adlandırılırsa önek değişebileceğinden sabit yazmak yerine sondan eşleştiriyoruz.
    result = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        capture_output=True, text=True,
    )
    for name in result.stdout.splitlines():
        if name.endswith("_n8n-data") or name == "n8n-data":
            return name
    print("HATA: n8n-data volume'ü bulunamadı. 'docker compose up -d' çalışmış mı?")
    sys.exit(1)


def main() -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = BACKUP_DIR / f"otomasyon-yedek-{stamp}.tar.gz"
    n8n_volume = find_n8n_volume()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        n8n_tar = tmp_path / "n8n-data.tar"

        print(f"[1/2] {n8n_volume} volume'ü dışa aktarılıyor...")
        run([
            "docker", "run", "--rm",
            "-v", f"{n8n_volume}:/data:ro",
            "-v", f"{tmp_path}:/backup",
            "alpine", "tar", "cf", "/backup/n8n-data.tar", "-C", "/data", ".",
        ])

        print("[2/2] Yayın geçmişi ve kullanılan konu listeleri kopyalanıyor...")
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        for filename in MEDIA_FILES:
            result = subprocess.run(
                [
                    "docker", "compose", "exec", "-T", "video-worker",
                    "cat", f"/data/media/{filename}",
                ],
                capture_output=True, cwd=str(ROOT),
            )
            if result.returncode == 0:
                (media_dir / filename).write_bytes(result.stdout)
            else:
                print(f"  [atlandı] {filename} bulunamadı (henüz oluşmamış olabilir).")

        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(n8n_tar, arcname="n8n-data.tar")
            for item in media_dir.iterdir():
                archive.add(item, arcname=f"media/{item.name}")

    size_kb = archive_path.stat().st_size / 1024
    print(f"\nTamam: {archive_path} ({size_kb:.0f} KB)")
    print("Geri yüklemek için: tar xzf <arşiv> ve n8n-data.tar'ı n8n-data volume'üne aç.")


if __name__ == "__main__":
    main()
