r"""Sızan sırları taşıyan yedek kopyaları AES-256-GCM ile mühürler.

Neden gerekli: `backups/otomasyon-yedek-*.tar.gz` ve `*.bundle` `.gitignore`'da
(`*.tar.gz`, `*.bundle`). Bu doğru — yoksa 130 MB'lık bundle ve 5.7 MB'lık n8n
veritabanı commit'lenebilirdi. Ama yan etkisi şu: **bu dosyalardaki sır ne
`secret_scan --history` ne de HEAD taraması tarafından görülür**. Ölçüm
(2026-11-02): bundle içinde `video-output/tiktok_session/` altında 941 nesne ve
süresi 2027-03-16'ya kadar geçerli `sessionid` çerezi duruyor.

Neden silmek yerine mühürlemek:
  * `*.bundle` geçmişi geri almanın TEK yolu (`git clone bundle geri-donus`).
    Döndürme (Telegram/n8n/TikTok) henüz yapılmadı; geri dönüş gerekebilir.
  * `backups/*.tar.gz` ise `verify_leak_rotation.py`'nin ölçüm aracıdır —
    silinirse döndürmenin yapılıp yapılmadığı ölçülemez (çıkış kodu 2).
  İkisi de gerekli, ikisi de tehlikeli. Mühürleme ikisini de çözer: dosya
  okunamaz hale gelir, ama parola ile geri döndürülebilir.

Biçim (`.sealed`):
    MAGIC(8) | sürüm(1) | salt(16) | nonce(12) | ciphertext+tag
Anahtar: scrypt(passphrase, salt, n=2**14, r=8, p=1) -> 32 bayt

Parola **hiçbir zaman** diske yazılmaz ve `.sealed` dosyasının yanına konmaz.
`--generate-key` ile üretilirse bir kez stderr'e basılır; kaybedilirse arşiv
açılamaz (bu, silmekle aynı sonuçtur — ama parolayı saklarsanız değil).

Kullanım:
    python scripts/seal_leak_copies.py --generate-key \
        --path ..\sosyal-medya-otomasyon-YEDEK.bundle --seal --delete-originals

    python scripts/seal_leak_copies.py --passphrase-env SEAL_KEY --open \
        --path ..\sosyal-medya-otomasyon-YEDEK.bundle.sealed --out geri-donus.bundle

Çıkış kodu: 0 = mühürlendi/açıldı ve doğrulandı, 1 = doğrulama başarısız, 2 = kullanım hatası.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import secrets
import sys
from pathlib import Path

MAGIC = b"LEAKSEAL"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
# scrypt maliyeti: 2**14 ≈ 16 MB, etkileşimli kullanım için ~50 ms.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=KEY_LEN, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
        passphrase.encode("utf-8")
    )


def seal_bytes(data: bytes, passphrase: str) -> bytes:
    """Ham baytları mühürler: MAGIC|sürüm|salt|nonce|ciphertext+tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not passphrase:
        raise ValueError("boş parola")
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    ciphertext = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, data, MAGIC)
    return MAGIC + bytes([VERSION]) + salt + nonce + ciphertext


def open_bytes(blob: bytes, passphrase: str) -> bytes:
    """Mührü açar. Yanlış parola / kurcalanmış dosya istisna fırlatır."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(MAGIC):
        raise ValueError("bu bir .sealed dosyası değil (MAGIC yok)")
    offset = len(MAGIC)
    version = blob[offset]
    if version != VERSION:
        raise ValueError(f"desteklenmeyen sürüm: {version}")
    offset += 1
    salt = blob[offset:offset + SALT_LEN]
    offset += SALT_LEN
    nonce = blob[offset:offset + NONCE_LEN]
    offset += NONCE_LEN
    try:
        return AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, blob[offset:], MAGIC)
    except InvalidTag as exc:
        # Yanlış parola ile kurcalanmış dosya ayırt edilemez — ikisi de aynı
        # istisnayı verir. Mesaj bunu dürüstçe söyler.
        raise ValueError("açılamadı: parola yanlış veya dosya kurcalanmış") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal_file(src: Path, dst: Path, passphrase: str, *, delete_original: bool) -> dict:
    """Dosyayı mühürler, **geri açıp** karşılaştırır, sonra isterse siler.

    Geri açıp karşılaştırmadan silmek yapılmaz: mühürleme bir yedekleme
    işlemidir, "yazdım" demek "okunabilir" demek değildir.
    """
    data = src.read_bytes()
    sealed = seal_bytes(data, passphrase)
    dst.write_bytes(sealed)

    # Doğrulama: diskten geri oku, aç, bayt bayt karşılaştır.
    reopened = open_bytes(dst.read_bytes(), passphrase)
    ok = _sha256(reopened) == _sha256(data)
    if not ok:
        raise RuntimeError(f"doğrulama başarısız: {dst} içeriği kaynakla eşleşmiyor")

    deleted = False
    if delete_original:
        src.unlink()
        deleted = True

    return {
        "src": str(src),
        "dst": str(dst),
        "src_bytes": len(data),
        "sealed_bytes": len(sealed),
        "sha256": _sha256(data)[:16],
        "verified": ok,
        "deleted": deleted,
    }

def _resolve_passphrase(args: argparse.Namespace) -> str | None:
    """Parolayı ortam değişkeninden, üretimle veya sorarak alır."""
    if args.passphrase_env:
        value = os.environ.get(args.passphrase_env, "")
        if not value:
            print(f"HATA: {args.passphrase_env} ortam değişkeni boş", file=sys.stderr)
            return None
        return value
    if args.generate_key:
        # 32 bayt entropi. stderr'e basılır ki `> dosya` yönlendirmesiyle
        # yanlışlıkla bir log dosyasına düşmesin.
        value = secrets.token_urlsafe(32)
        print("=" * 68, file=sys.stderr)
        print("ÜRETİLEN PAROLA — BİR KEZ GÖSTERİLİR, DİSKE YAZILMAZ", file=sys.stderr)
        print(value, file=sys.stderr)
        print("Parola yöneticinize kaydedin. Kaybolursa arşiv açılamaz;", file=sys.stderr)
        print("bu, dosyayı silmekle aynı sonucu verir.", file=sys.stderr)
        print("=" * 68, file=sys.stderr)
        return value
    value = getpass.getpass("Parola: ")
    if not value:
        print("HATA: boş parola", file=sys.stderr)
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sızan sırları taşıyan yedek kopyaları mühürler (AES-256-GCM).")
    parser.add_argument("--path", required=True, help="mühürlenecek/açılacak dosya")
    parser.add_argument("--seal", action="store_true", help="mühürle (.sealed üret)")
    parser.add_argument("--open", dest="open_", action="store_true", help="mührü aç")
    parser.add_argument("--out", help="çıktı yolu (varsayılan: <path>.sealed / uzantısız)")
    parser.add_argument("--passphrase-env", help="parolayı bu ortam değişkeninden oku")
    parser.add_argument("--generate-key", action="store_true",
                        help="rastgele parola üret ve stderr'e bir kez bas")
    parser.add_argument("--delete-originals", action="store_true",
                        help="doğrulama geçtikten SONRA kaynağı sil (yalnız --seal)")
    args = parser.parse_args(argv)

    if args.seal == args.open_:
        print("HATA: tam olarak biri verilmeli: --seal veya --open", file=sys.stderr)
        return 2
    if args.delete_originals and not args.seal:
        print("HATA: --delete-originals yalnız --seal ile anlamlı", file=sys.stderr)
        return 2

    path = Path(args.path)
    if not path.is_file():
        print(f"HATA: dosya yok: {path}", file=sys.stderr)
        return 2

    passphrase = _resolve_passphrase(args)
    if passphrase is None:
        return 2

    if args.seal:
        dst = Path(args.out) if args.out else path.with_name(path.name + ".sealed")
        if dst.exists():
            print(f"HATA: hedef zaten var, üzerine yazmıyorum: {dst}", file=sys.stderr)
            return 2
        info = seal_file(path, dst, passphrase, delete_original=args.delete_originals)
        print(f"mühürlendi : {info['src']}")
        print(f"  -> {info['dst']}")
        print(f"  kaynak {info['src_bytes']:,} B -> mühür {info['sealed_bytes']:,} B")
        print(f"  sha256(ilk 16): {info['sha256']}")
        print(f"  geri açılıp doğrulandı: {'EVET' if info['verified'] else 'HAYIR'}")
        print(f"  kaynak silindi: {'EVET' if info['deleted'] else 'HAYIR'}")
        return 0

    dst = Path(args.out) if args.out else path.with_name(
        path.name[:-len(".sealed")] if path.name.endswith(".sealed") else path.name + ".unsealed")
    if dst.exists():
        print(f"HATA: hedef zaten var, üzerine yazmıyorum: {dst}", file=sys.stderr)
        return 2
    try:
        plain = open_bytes(path.read_bytes(), passphrase)
    except ValueError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1
    dst.write_bytes(plain)
    print(f"açıldı     : {path}")
    print(f"  -> {dst} ({len(plain):,} B)")
    print(f"  sha256(ilk 16): {_sha256(plain)[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

