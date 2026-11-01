"""
TikTok web oturumunu konteynere aktarır (veya yerel kullanım için doğrular).

Neden gerekli: `tiktok_browser.py` bir Playwright `user_data_dir` oturumu
kullanıyor. O oturum imaja GÖMÜLEMEZ (cookie'ler sırdır; `.gitignore` ve
`.dockerignore` bunu açıkça dışlar). Bu yüzden konteynere kalıcı bir volume
olarak bağlanır: `tiktok-session` (compose'da `TIKTOK_SESSION_DIR=/data/tiktok-session`).

Akış:

1. Oturum yoksa önce bir kez giriş yap (görünür tarayıcı gerekir, headless olmaz):

       python scripts/tiktok_browser_login.py

2. Oturumu konteyner volume'una aktar:

       python scripts/refresh_tiktok_session.py --upload

   `docker cp` yerine `docker run --rm -v <volume>:/dst ...` kullanılıyor:
   `docker cp` çalışan konteyner gerektirir ve volume adı üzerinden yazmayı
   desteklemez.

3. Konteynerdeki oturumun görünür olduğunu doğrula:

       python scripts/refresh_tiktok_session.py --verify

Bu betik SIR YAZDIRMAZ: yalnızca dosya sayısı ve bayt miktarı raporlanır.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_DIR = REPO_ROOT / "video-output" / "tiktok_session"

#: compose'daki volume adı ve konteyner içi hedef (video-worker servisiyle aynı).
CONTAINER_TARGET = "/data/tiktok-session"


def _compose_volume_name() -> str:
    """`docker compose` proje önekiyle gerçek volume adını sorar.

    Volume adı `<proje>_tiktok-session` olur; proje adı dizin adından gelir ve
    kullanıcı `-p` ile değiştirebilir. Tahmin etmek yerine Docker'a soruyoruz.
    """
    try:
        out = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"`docker volume ls` calistirilamadi: {exc}") from exc

    candidates = [n for n in out.stdout.splitlines() if n.endswith("tiktok-session")]
    if not candidates:
        raise SystemExit(
            "`tiktok-session` volume'u bulunamadi.\n"
            "  Once `docker compose up -d` calistirin (volume tanimi compose'da)."
        )
    if len(candidates) > 1:
        raise SystemExit(
            "Birden fazla `tiktok-session` volume'u var, hangisi belirsiz:\n  "
            + "\n  ".join(candidates)
            + "\n  `--volume` ile acikca belirtin."
        )
    return candidates[0]


def _session_summary(path: Path) -> tuple[int, int]:
    """(dosya sayisi, toplam bayt) — icerik okunmaz, dosya adi yazdirilmaz."""
    if not path.exists():
        return (0, 0)
    files = [p for p in path.rglob("*") if p.is_file()]
    return (len(files), sum(p.stat().st_size for p in files))


def cmd_verify(args: argparse.Namespace) -> int:
    """Yerel ve konteyner tarafindaki oturumun varligini raporlar."""
    local = Path(args.session_dir).expanduser()
    count, size = _session_summary(local)
    print(f"Yerel oturum: {local}")
    print(f"  {count} dosya, {size / 1024:.1f} KB" if count else "  (yok)")

    try:
        resolved = args.volume or _compose_volume_name()
    except SystemExit as exc:
        print(f"UYARI: volume cozumlenemedi: {exc}")
        return 1

    print(f"Konteyner volume: {resolved}")
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{resolved}:{CONTAINER_TARGET}:ro",
            "python:3.12-slim",
            "sh", "-c",
            f"find {CONTAINER_TARGET} -type f | wc -l; du -sk {CONTAINER_TARGET} 2>/dev/null | cut -f1",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        print(f"UYARI: volume okunamadi: {result.stderr.strip()[:200]}")
        return 1

    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    remote_count = int(lines[0]) if lines else 0
    remote_kb = int(lines[1]) if len(lines) > 1 else 0
    print(f"  {remote_count} dosya, {remote_kb} KB" if remote_count else "  (bos)")

    if remote_count == 0 and count > 0:
        print("\nHATA: Oturum yerelde var ama konteynerde YOK.")
        print("  TikTok web yolu konteynerde calismaz. Duzeltmek icin:")
        print("  python scripts/refresh_tiktok_session.py --upload")
        return 1
    if remote_count > 0:
        print("\nTAMAM: Konteynerde oturum gorunuyor.")
        print("  Not: cerezler zamanla suresi dolar; yukleme 'suresi dolmus' derse")
        print("  `tiktok_browser_login.py` ile yeniden giris yapip tekrar --upload edin.")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    """Yerel oturumu konteyner volume'una kopyalar (uzerine yazar)."""
    local = Path(args.session_dir).expanduser()
    count, size = _session_summary(local)
    if count == 0:
        print(f"HATA: Yerel oturum bos: {local}")
        print("  Once bir kez giris yapin: python scripts/tiktok_browser_login.py")
        return 1
    print(f"Kaynak: {local} ({count} dosya, {size / 1024:.1f} KB)")

    try:
        volume = args.volume or _compose_volume_name()
    except SystemExit as exc:
        print(f"HATA: {exc}")
        return 1
    print(f"Hedef volume: {volume} -> {CONTAINER_TARGET}")

    if not args.dry_run:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{volume}:{CONTAINER_TARGET}",
                "-v", f"{local}:{CONTAINER_TARGET}-src:ro",
                "python:3.12-slim",
                "sh", "-c",
                # Eski dosyalari temizle ki silinmis cerezler geri gelmesin.
                f"rm -rf {CONTAINER_TARGET}/* && cp -a {CONTAINER_TARGET}-src/. {CONTAINER_TARGET}/",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            print(f"HATA: kopyalama basarisiz: {result.stderr.strip()[:400]}")
            return 1
        print("TAMAM: aktarildi.")
    else:
        print("--dry-run: hicbir sey kopyalanmadi.")

    print("  Dogrulamak icin: python scripts/refresh_tiktok_session.py --verify")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TikTok web oturumunu konteyner volume'una aktarir / dogrular",
    )
    parser.add_argument(
        "--session-dir",
        default=str(DEFAULT_SESSION_DIR),
        help=f"Yerel oturum dizini (varsayilan: {DEFAULT_SESSION_DIR})",
    )
    parser.add_argument(
        "--volume",
        default="",
        help="Docker volume adi (bossa otomatik bulunur)",
    )
    parser.add_argument("--upload", action="store_true", help="Yerel oturumu volume'a kopyala")
    parser.add_argument("--verify", action="store_true", help="Yerel ve konteyner oturumunu karsilastir")
    parser.add_argument("--dry-run", action="store_true", help="Kopyalama yapma, yalnizca plani goster")
    args = parser.parse_args()

    if not (args.upload or args.verify):
        parser.print_help()
        return 2
    if args.upload:
        return cmd_upload(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
