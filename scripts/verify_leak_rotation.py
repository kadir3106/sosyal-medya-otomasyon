"""Sızan sırların gerçekten döndürülüp döndürülmediğini ölçer.

Neden gerekli: `docs/SIZINTI_TEMIZLIGI.md` Bölüm 2'deki adımlar panel işi ve
elle yapılıyor. Yapıldı mı yapılmadı mı tahmin etmenin bir yolu yoktu — bu
betik ölçüyor. Hiçbir sır değeri yazdırılmaz; yalnızca sha256'nın ilk 8 hanesi
(parmak izi), uzunluk ve "geçerli/iptal" sonucu.

Kaynak: `backups/otomasyon-yedek-2026-09-05.tar.gz` içindeki n8n yedeği
(`n8n-data.tar` → `database.sqlite` + `config`). Şifre çözme, n8n'in kendi
`CipherAes256CBC` uygulamasıdır:
    base64( "Salted__" || salt(8) || AES-256-CBC(gövde) )
    derivedKey/iv <- EVP_BytesToKey(MD5, password=encryptionKey||salt)

Kullanım:
    python scripts/verify_leak_rotation.py              # özet tablo
    python scripts/verify_leak_rotation.py --telegram   # yalnız Telegram
    python scripts/verify_leak_rotation.py --tiktok     # yalnız TikTok çerezleri
    python scripts/verify_leak_rotation.py --n8n        # yalnız n8n parolası

Çıkış kodu: 0 = sızan her şey etkisiz, 1 = hâlâ geçerli sır var, 2 = ölçülemedi.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sqlite3
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARBALL = ROOT / "backups" / "otomasyon-yedek-2026-09-05.tar.gz"
TIKTOK_PROFILE = ROOT / "video-output" / "tiktok_session"

MAGIC = b"Salted__"  # n8n'in sabit başlığı (hex 53616c7465645f5f)


def fp(value: str) -> str:
    """Sırrın kendisini değil, kimliğini gösterir."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def read_env() -> dict[str, str]:
    """`.env`'i BOM'a dayanıklı okur.

    `encoding='utf-8'` ile ilk satır `\\ufeffTELEGRAM_BOT_TOKEN` olur ve
    `startswith` ile yapılan aramalar sessizce boş döner — bu, ilk ölçümde
    token'ı "yok" sandırdı.
    """
    path = ROOT / ".env"
    if not path.exists():
        return {}
    text = io.open(path, encoding="utf-8-sig").read()
    return {
        m.group(1): m.group(2).strip().strip('"').strip("'")
        for m in re.finditer(r"(?m)^([A-Z0-9_]+)=(.*)$", text)
    }


def _key_and_iv(salt: bytes, key: str) -> tuple[bytes, bytes]:
    password = key.encode("latin-1", "replace") + salt
    h1 = hashlib.md5(password).digest()
    h2 = hashlib.md5(h1 + password).digest()
    return h1 + h2, hashlib.md5(h2 + password).digest()


def decrypt_n8n(data: str, key: str) -> str:
    """n8n `CipherAes256CBC.decrypt` birebir kopyası."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # requirements.txt'te yok — net mesaj ver
        raise RuntimeError(
            "`cryptography` gerekli: pip install cryptography"
        ) from exc

    raw = base64.b64decode(data)
    if len(raw) < 16 or raw[:8] != MAGIC:
        raise ValueError("n8n formatı değil (Salted__ başlığı yok)")
    derived_key, iv = _key_and_iv(raw[8:16], key)
    decipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv)).decryptor()
    padded = decipher.update(raw[16:]) + decipher.finalize()
    pad = padded[-1]
    if not 1 <= pad <= 16 or padded[-pad:] != bytes([pad]) * pad:
        raise ValueError("padding bozuk (anahtar yanlış)")
    return padded[:-pad].decode("utf-8")


def load_n8n_store() -> tuple[str, list[dict], dict]:
    """Arşivi açar: (encryptionKey, credential listesi, user satırı)."""
    if not TARBALL.exists():
        raise FileNotFoundError("arşiv yok: %s" % TARBALL.relative_to(ROOT))

    tmp = Path(tempfile.mkdtemp(prefix="verify-rotation-"))
    with tarfile.open(TARBALL, "r:gz") as outer:
        outer.extractall(tmp, filter="data")

    inner = next(tmp.rglob("n8n-data.tar"), None)
    if inner is None:
        raise FileNotFoundError("iç arşiv `n8n-data.tar` bulunamadı")
    with tarfile.open(inner, "r") as nested:
        nested.extractall(tmp / "n8n", filter="data")

    cfg = next((tmp / "n8n").rglob("config"))
    key = json.loads(cfg.read_text(encoding="utf-8"))["encryptionKey"]

    con = sqlite3.connect(str(next((tmp / "n8n").rglob("database.sqlite"))))
    con.row_factory = sqlite3.Row
    creds = [dict(r) for r in con.execute(
        "SELECT id, name, type, data FROM credentials_entity")]
    users = [dict(r) for r in con.execute("SELECT * FROM user")]
    con.close()
    return key, creds, (users[0] if users else {})


def check_telegram(key: str, creds: list[dict], env: dict[str, str]) -> list[str]:
    """Sızan bot token'ı hâlâ çalışıyor mu? (salt-okunur `getMe`)"""
    lines: list[str] = []
    tele = next((c for c in creds if c["type"] == "telegramApi"), None)
    if tele is None:
        return ["Telegram credential'ı arşivde yok — atlandı"]

    leaked = json.loads(decrypt_n8n(tele["data"], key)).get("accessToken", "")
    current = env.get("TELEGRAM_BOT_TOKEN", "")
    lines.append("sızan token    : fp=%s uzunluk=%d" % (fp(leaked), len(leaked)))
    lines.append("`.env` token   : fp=%s uzunluk=%d  (aynı mı: %s)"
                 % (fp(current or ""), len(current or ""), leaked == current))

    for label, token in (("SIZAN", leaked), (".env", current)):
        if not token:
            lines.append("%-6s : token yok" % label)
            continue
        url = "https://api.telegram.org/bot%s/getMe" % token
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                body = json.load(resp)
            username = (body.get("result") or {}).get("username")
            lines.append("%-6s : HTTP %d  >>> HALA GECERLI <<<  bot=@%s"
                         % (label, resp.status, username))
        except urllib.error.HTTPError as exc:
            lines.append("%-6s : HTTP %d  iptal edilmiş (401 = başarılı döndürme)"
                         % (label, exc.code))
        except Exception as exc:  # noqa: BLE001 - ağ hatası ölçümü durdurmamalı
            lines.append("%-6s : bağlantı hatası (%s)" % (label, type(exc).__name__))
    return lines


def check_n8n_password(creds_user: dict, env: dict[str, str]) -> list[str]:
    """Sızan bcrypt hash'i hâlâ mevcut `N8N_PASSWORD` ile açılıyor mu?"""
    stored = creds_user.get("password") or ""
    current = env.get("N8N_PASSWORD", "")
    lines = ["hesap          : %s" % creds_user.get("email")]
    lines.append("hash           : %s… uzunluk=%d" % (stored[:7], len(stored)))
    lines.append("`.env` parola  : uzunluk=%d" % len(current))
    if not stored.startswith("$2") or not current:
        lines.append("SONUC          : karşılaştırılamadı (bcrypt değil veya parola yok)")
        return lines
    try:
        import bcrypt
    except ImportError:
        lines.append("SONUC          : `bcrypt` kurulu değil — `pip install bcrypt`")
        return lines
    if bcrypt.checkpw(current.encode(), stored.encode()):
        lines.append("SONUC          : >>> HALA AYNI <<< arşivdeki hash mevcut parolayla açılıyor")
    else:
        lines.append("SONUC          : parola değişmiş, arşivdeki hash artık geçersiz")
    return lines


def check_tiktok() -> list[str]:
    """Profil diskte mi ve çerezlerin son kullanma tarihi geçmiş mi?"""
    if not TIKTOK_PROFILE.exists():
        return ["profil silinmiş — ✅ (video-output/tiktok_session yok)"]

    import datetime
    import shutil

    files = [p for p in TIKTOK_PROFILE.rglob("*") if p.is_file()]
    lines = ["profil         : HALA DISKTE — %d dosya, %.1f MB"
             % (len(files), sum(p.stat().st_size for p in files) / 1e6)]

    ck = next(TIKTOK_PROFILE.rglob("Network/Cookies"), None)
    if ck is None:
        lines.append("Cookies        : bulunamadı")
        return lines

    tmp = Path(tempfile.mkdtemp(prefix="verify-ck-")) / "Cookies"
    shutil.copy2(ck, tmp)  # kilitli db'yi doğrudan açmak kilit hatası verir
    con = sqlite3.connect(str(tmp))
    rows = list(con.execute(
        "SELECT host_key, name, expires_utc FROM cookies WHERE host_key LIKE '%tiktok%'"))
    con.close()

    def as_date(chromium_us: int) -> str:
        if not chromium_us:
            return "oturum"
        epoch = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=chromium_us)
        return epoch.strftime("%Y-%m-%d")

    important = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt", "uid_tt"}
    lines.append("tiktok çerezi  : %d adet" % len(rows))
    for host, name, expires in rows:
        if name in important:
            lines.append("  %-16s %-12s bitiş=%s" % (host, name, as_date(expires)))
    lines.append("SONUC          : çerezler silinene/döndürülene kadar geçerli kalır "
                 "-> TikTok'ta *log out of all devices*")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sızan sırların döndürülüp döndürülmediğini ölçer (sır yazdırmaz).")
    parser.add_argument("--telegram", action="store_true", help="yalnız Telegram bot token'ı")
    parser.add_argument("--n8n", action="store_true", help="yalnız n8n sahip parolası")
    parser.add_argument("--tiktok", action="store_true", help="yalnız TikTok profili")
    args = parser.parse_args(argv)

    only = args.telegram or args.n8n or args.tiktok
    do_all = not only
    env = read_env()
    failures: list[str] = []

    print("=" * 66)
    print("Sızıntı döndürme doğrulaması — ölçüm, tahmin değil")
    print("=" * 66)

    if do_all or args.telegram or args.n8n:
        try:
            key, creds, user = load_n8n_store()
        except (FileNotFoundError, ValueError) as exc:
            print("\n[!] n8n arşivi okunamadı: %s" % exc)
            print("    (arşiv silinmişse bu beklenir; döndürme zaten yapılmış olabilir)")
            return 2
        except RuntimeError as exc:
            print("\n[!] %s" % exc)
            print("    Python 3.13'te `pip install cryptography` yeterli.")
            return 2

    if do_all or args.telegram:
        print("\n--- Telegram bot token'ı ---")
        lines = check_telegram(key, creds, env)
        print("\n".join(lines))
        if any("HALA GECERLI" in line for line in lines):
            failures.append("telegram")

    if do_all or args.n8n:
        print("\n--- n8n sahip parolası ---")
        lines = check_n8n_password(user, env)
        print("\n".join(lines))
        if any("HALA AYNI" in line for line in lines):
            failures.append("n8n-parola")

    if do_all or args.tiktok:
        print("\n--- TikTok tarayıcı profili ---")
        lines = check_tiktok()
        print("\n".join(lines))
        if any("HALA DISKTE" in line for line in lines):
            failures.append("tiktok-profil")

    print("\n" + "=" * 66)
    if failures:
        print("DÖNDÜRME TAMAM DEĞİL. Açık kalan: %s" % ", ".join(failures))
        print("Adımlar: docs/SIZINTI_TEMIZLIGI.md → Bölüm 2")
        return 1
    print("Tüm sızan sırlar etkisiz. ✅")
    return 0


if __name__ == "__main__":
    # Windows konsolu cp1254/cp850 olabilir; `→` gibi karakterler o zaman
    # UnicodeEncodeError ile betiği çökertir. UTF-8'e geç, olmazsa değiştir.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())



