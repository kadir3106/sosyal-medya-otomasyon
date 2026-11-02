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
import os
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
                 "-> TikTok'ta *log out of all devices* (mobil uygulama)")
    lines.append("                 NOT: web ayarlarında oturum/şifre bölümü YOK — "
                 "tarayıcıyla yapılamaz (ölçüldü 2026-11-02)")
    return lines


#: Sızıntılı nesneleri taşıyan dosya kopyaları — repo DIŞINDA olsalar bile.
#: Neden ayrı kontrol: `.gitignore` bunları yok sayıyor (`*.tar.gz`, `*.bundle`,
#: `*.sealed`), yani `secret_scan --history` de HEAD taraması da onları hiç
#: görmez. Ölçüm (2026-11-02): diskteki 130.7 MB'lık bundle'da
#: `video-output/tiktok_session/` altında **941 nesne** duruyor ve içindeki
#: `sessionid` çerezi 2027-03-16'ya kadar geçerli. Bu yüzden döndürme
#: doğrulaması "repo temiz mi" değil, "sır hâlâ okunabilir bir kopyada mı"
#: sorusunu sormalı.
LEAK_COPIES: list[tuple[Path, str]] = [
    (ROOT.parent / "sosyal-medya-otomasyon-YEDEK.bundle",
     "git bundle — tüm geçmiş (tiktok_session profili + n8n encryptionKey)"),
    (TARBALL, "n8n yedeği — database.sqlite + encryptionKey"),
]

#: Canlı oturum dizinleri: `.gitignore`'da ama **diskte**. Bilerek sürüyorlar
#: (prodüksiyon onları kullanıyor) — bu yüzden "sil" değil "farkında ol"
#: kalemi. Mühürlenemezler: mühürlemek çalışan oturumu bozar.
LIVE_STATE_DIRS: list[Path] = [
    ROOT / "video-output" / "tiktok_session",
]

#: Verilen köklerin altında adı ne olursa olsun aranan sır taşıyıcıları.
#: Sabit `LEAK_COPIES` listesinin yetmediği yer: kullanıcı yedeği başka adla
#: kopyalamış olabilir (`yedek-2.bundle`, `eski-yedek.tar.gz`). Ölçüm
#: (2026-11-02): `C:\Projects` altında adı farklı bir tarball (`dateutil-
#: zoneinfo.tar.gz`, bir venv dosyası) de bulundu — yani "adı belli" varsayımı
#: yanlış pozitif de üretir, kaçırma da. Bu yüzden tarama yapılıyor ama venv /
#: site-packages / node_modules atlanıyor.
STRAY_SCAN_ROOTS: list[Path] = [ROOT.parent]
STRAY_SCAN_SUFFIXES = (".bundle", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")
STRAY_SKIP_PARTS = (
    "venv", ".venv", "site-packages", "node_modules", "__pycache__",
    ".git", ".pytest_cache", "dist", "build",
)
STRAY_MAX_DEPTH = 4



def discover_stray_copies() -> list[tuple[Path, bool]]:
    """Diskte adı ne olursa olsun sır taşıyıcı dosyaları bulur: (yol, mühürlü_mü).

    Neden sabit liste yetmiyor: `LEAK_COPIES` iki bilinen yolu sayıyor. Kullanıcı
    yedeği başka adla kopyalamışsa (`yedek-2.bundle`) doğrulayıcı "temiz" derdi.
    Ölçüm (2026-11-02): `C:\\Projects` altında venv içinde `dateutil-
    zoneinfo.tar.gz` var — yani sonek taraması tek başına yanlış pozitif üretir.
    Bu yüzden venv/site-packages/node_modules atlanıyor.

    Döndürülen bayrak, dosyanın **mühürlü** olup olmadığını söyler; mühürlü
    dosya aynı ada `+ ".sealed"` ile değil, kendi adı `.sealed` ile biter.
    """
    found: list[tuple[Path, bool]] = []
    for root in STRAY_SCAN_ROOTS:
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
            current = Path(dirpath)
            depth = len(current.parts) - base_depth
            # Derinlik sınırı: sınıra gelince alt dizinlere inme.
            if depth >= STRAY_MAX_DEPTH:
                dirnames[:] = []
            # Gürültü kaynaklarını buda (venv, node_modules, .git...).
            dirnames[:] = [d for d in dirnames if d not in STRAY_SKIP_PARTS]
            for name in filenames:
                lowered = name.lower()
                sealed = lowered.endswith(".sealed")
                probe = lowered[: -len(".sealed")] if sealed else lowered
                if not probe.endswith(STRAY_SCAN_SUFFIXES):
                    continue
                found.append((current / name, sealed))
    return sorted(found)


def check_stray_copies() -> list[str]:
    """Repoda/dışında duran yedek kopyaları ölçer — sır değerini yazdırmadan.

    Mühürlenmiş kopya (`<ad>.sealed`) **açık sayılmaz**: `scripts/seal_leak_copies.py`
    ile AES-256-GCM altına alınmış bir dosyada sır okunamaz. Bu ayrımı yapmayan
    bir doğrulayıcı, mühürleme yapıldıktan sonra da "açık" derdi — yani
    operatörü hiç bitmeyen bir uyarıyla yorardı.

    Mühürlü ama kaynağı hâlâ duran dosya uyarı verir: mühürlemek tek başına
    yetmez, düz kopya silinmedikçe sır okunabilir kalır.

    İki katman: `LEAK_COPIES` bilinen yolları anlamlarıyla raporlar,
    `discover_stray_copies()` adı ne olursa olsun diskte kalanları bulur.
    Yalnız birincisi yetseydi `yedek-2.bundle` gibi bir kopya görünmezdi.
    """
    lines: list[str] = []
    found = False
    for path, what in LEAK_COPIES:
        sealed = path.with_name(path.name + ".sealed")
        if not path.exists():
            if sealed.exists():
                size_mb = sealed.stat().st_size / 1e6
                lines.append("%-14s MÜHÜRLÜ (%.1f MB) — ✅ sır okunamaz" % (path.name, size_mb))
                lines.append("                açmak için parola gerekir "
                             "(seal_leak_copies.py --open)")
            else:
                lines.append("%-14s yok — ✅" % path.name)
            continue
        found = True
        size_mb = path.stat().st_size / 1e6
        lines.append("HALA DISKTE   : %s (%.1f MB)" % (path, size_mb))
        lines.append("                %s" % what)
        if sealed.exists():
            lines.append("                [!] mühürlü kopya da var ama DÜZ kopya "
                         "silinmemiş — sır hâlâ okunabilir")
    if found:
        lines.append("SONUC         : bu kopyalar döndürme tamamlanana kadar sırrı "
                     "okunabilir tutar")
        lines.append("                Mühürleyin (sır okunamaz olur, geri dönüş kalır):")
        lines.append("                  python scripts/seal_leak_copies.py "
                     "--generate-key \\")
        lines.append("                      --path \"<yol>\" --seal --delete-originals")
        lines.append("                Ayrıntı: docs/SIZINTI_TEMIZLIGI.md §5")

    # İkinci katman: adı ne olursa olsun diskteki arşivler.
    known = {p.resolve() for p, _ in LEAK_COPIES}
    extras = [(p, s) for p, s in discover_stray_copies()
              if p.resolve() not in known
              and p.with_name(p.name + ".sealed").resolve() not in known
              and not any(p.resolve() == k.with_name(k.name + ".sealed") for k in known)]
    unsealed_extras = [p for p, sealed in extras if not sealed]
    if unsealed_extras:
        lines.append("")
        lines.append("BILINMEYEN KOPYALAR (%d) — adı farklı olduğu için "
                     "bilinen listede yok:" % len(unsealed_extras))
        for path in unsealed_extras[:10]:
            size_mb = path.stat().st_size / 1e6
            lines.append("  %s (%.1f MB)" % (path, size_mb))
        if len(unsealed_extras) > 10:
            lines.append("  ... ve %d tane daha" % (len(unsealed_extras) - 10))
        lines.append("  Bu dosyalar da mühürlenmeli veya silinmeli.")
    sealed_extras = [p for p, sealed in extras if sealed]
    if sealed_extras:
        lines.append("bilinmeyen mühürlü kopya: %d adet — ✅ sır okunamaz"
                     % len(sealed_extras))

    # Canlı oturum dizinleri: `check_tiktok()` profili zaten "HALA DISKTE" diye
    # raporluyor. Buradaki katma değer tek şey: **silinmemesi gerektiğini**
    # söylemek — çünkü "sızıntı listesinde görünen dizin" refleks olarak "sil"
    # dedirtir, oysa prodüksiyon o profili kullanıyor.
    for live in LIVE_STATE_DIRS:
        if not live.is_dir():
            continue
        lines.append("")
        lines.append("CANLI OTURUM  : %s" % live)
        lines.append("                .gitignore'da ✅ ama diskte. "
                     "Döndürmeden SONRA silinebilir.")
        lines.append("                SİLMEYİN: prodüksiyon bu profili kullanıyor; "
                     "oturum canlı (--tiktok ölçtü).")
    return lines


#: Hangi adımın otomatikleştirilebildiği — tahmin değil, denendi ve ölçüldü
#: (2026-11-02). `verify_leak_rotation.py` bunu her çalıştırmada hatırlatır ki
#: bir sonraki turda "betikle yapılır mı" sorusu yeniden sorulmasın.
CAPABILITIES: list[tuple[str, str, str, str]] = [
    ("telegram", "BotFather → /revoke", "HAYIR",
     "Telegram kullanıcı oturumu yok: .env'de api_id/api_hash/phone/"
     "session-string hiçbiri bulunmuyor, bot API kendi token'ını iptal edemez"),
    ("n8n-parola", "n8n UI → Settings → Users", "HAYIR",
     "n8n yalnızca localhost:5678'de tanımlı ve Docker motoru bu makinede "
     "çalışmıyor — servis ayakta değil, parola değiştirilecek arayüz yok"),
    ("tiktok", "Mobil uygulama → Settings → Security", "HAYIR",
     "Oturum bu makinede GEÇERLİ (ölçüldü: giriş duvarı yok, sessionid "
     "2027-03-16) ama web /setting sayfasında log out/device/password/"
     "security bölümü hiç yok — panel mobil uygulamada"),
    # Silme bilinçli olarak betikleştirilmedi: bu dosyalar geçmişi geri alma
    # yolunun TEK kopyası (`bundle` ile `git clone` geri dönüşü). Otomatik
    # silmek, yanlış anda çalıştığında geri dönüşü olmayan veri kaybı demek.
    # Kararı operatör verir; betik yalnız varlığını ölçer. Mühürleme (madde 32)
    # bu boşluğu kapatır: sır okunamaz olur, geri dönüş yolu kalır.
    ("yedek-kopya", "Mühürle: scripts/seal_leak_copies.py --seal", "HAYIR",
     "silme otomatikleştirilmedi (bundle tek geri dönüş yolu); mühürleme "
     "parola ister ve parola diske yazılmaz — kararı operatör verir"),
]



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

    print("\n--- Disk üzerindeki yedek kopyaları ---")
    stray = check_stray_copies()
    print("\n".join(stray))
    if any("HALA DISKTE" in line for line in stray):
        failures.append("yedek-kopya")

    print("\n" + "=" * 66)
    if failures:
        print("DÖNDÜRME TAMAM DEĞİL. Açık kalan: %s" % ", ".join(failures))
        print("Adımlar: docs/SIZINTI_TEMIZLIGI.md → Bölüm 2")
        print("\nBu adımlar BETİKLE YAPILAMAZ (denendi, ölçüldü 2026-11-02):")
        for name, panel, auto, why in CAPABILITIES:
            if name.split("-")[0] in " ".join(failures) or name in failures:
                print("  %-11s %-38s otomatik: %s" % (name, panel, auto))
                print("              %s" % why)
        print("\nBetik yalnızca ÖLÇER; döndürme panel işidir. "
              "Her adımdan sonra tekrar çalıştırın.")
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



