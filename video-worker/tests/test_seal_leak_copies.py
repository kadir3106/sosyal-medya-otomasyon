"""Mühürleme — sır okunamaz oluyor mu, geri döndürülebiliyor mu?

Bu betiğin tehlikeli tarafı yanlış tarafa yanlış cevap vermesi:
  * "mühürledim" deyip okunabilir bırakırsa sır açıkta kalır (asıl risk),
  * geri açılamazsa kullanıcı geçmişini kaybeder (silmekten farkı kalmaz).
Bu yüzden iki yön de ölçülüyor. Parola ve düz metin literal yazılmıyor —
dosya izlenen bir dosya, `secret_scan` kendi fixture'ını bulgu görmesin
(bkz. test_secret_scan.py; ilk denemede tam bu oldu).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from seal_leak_copies import (  # noqa: E402
    MAGIC,
    VERSION,
    main,
    open_bytes,
    seal_bytes,
    seal_file,
)


def _needs_crypto():
    """`cryptography` prodüksiyon imajında yok — atlanmalı, düşmemeli."""
    pytest.importorskip("cryptography.hazmat.primitives.ciphers.aead")


def _secret_ish() -> bytes:
    """Çalışma anında üretilen sahte sır — literal yazılmıyor."""
    return os.urandom(64)


def test_sealed_output_does_not_contain_plaintext():
    """Asıl iddia: mühürlü dosyada düz metin GEÇMEZ.

    Zayıf bir uygulama (ör. XOR, ya da başlığa özet koymak) bu testi geçemez.
    """
    _needs_crypto()
    plain = _secret_ish()
    marker = b"tiktok-sessionid-DELETE-ME"
    payload = plain + marker
    passphrase = os.urandom(24).hex()

    sealed = seal_bytes(payload, passphrase)

    assert marker not in sealed
    assert payload[:16] not in sealed
    assert sealed.startswith(MAGIC)
    assert sealed[len(MAGIC)] == VERSION


def test_roundtrip_returns_exact_bytes():
    """Geri döndürme bayt bayt aynı olmalı — 'çalışıyor gibi' değil, aynı."""
    _needs_crypto()
    payload = _secret_ish() * 100  # 6400 B, tek bloktan büyük
    passphrase = os.urandom(24).hex()

    assert open_bytes(seal_bytes(payload, passphrase), passphrase) == payload


def test_wrong_passphrase_fails_loudly():
    """Yanlış parola sessizce boş/yarım veri döndürmemeli — hata vermeli."""
    _needs_crypto()
    sealed = seal_bytes(_secret_ish(), os.urandom(24).hex())
    other = os.urandom(24).hex()

    with pytest.raises(ValueError, match="parola yanlış veya dosya kurcalanmış"):
        open_bytes(sealed, other)


def test_tampered_ciphertext_is_rejected():
    """Tek bayt değişirse AES-GCM tag tutmaz — kurcalama fark edilmeli."""
    _needs_crypto()
    passphrase = os.urandom(24).hex()
    sealed = bytearray(seal_bytes(_secret_ish(), passphrase))
    sealed[-1] ^= 0x01

    with pytest.raises(ValueError):
        open_bytes(bytes(sealed), passphrase)


def test_empty_passphrase_refused():
    """Boş parola = parolasız arşiv. Reddedilmeli, uyarıyla geçilmemeli."""
    _needs_crypto()
    with pytest.raises(ValueError, match="boş parola"):
        seal_bytes(_secret_ish(), "")


def test_not_a_sealed_file_rejected():
    """Düz bir dosyayı 'mühürlü' sanıp açmaya çalışmak sessiz geçmemeli."""
    _needs_crypto()
    with pytest.raises(ValueError, match="MAGIC yok"):
        open_bytes(b"just a normal tarball, nothing sealed here", "x")


def test_seal_file_verifies_before_deleting(tmp_path):
    """`--delete-originals` yalnız doğrulama geçince siler.

    Silinen bir kaynağın geri gelmediği düşünülürse sıra önemli: önce mühürle,
    diskten geri oku, aç, karşılaştır — sonra sil.
    """
    _needs_crypto()
    src = tmp_path / "yedek.tar.gz"
    payload = _secret_ish() * 10
    src.write_bytes(payload)
    dst = tmp_path / "yedek.tar.gz.sealed"
    passphrase = os.urandom(24).hex()

    info = seal_file(src, dst, passphrase, delete_original=True)

    assert info["verified"] is True
    assert info["deleted"] is True
    assert not src.exists()
    # Silinen düz metin, mühürden geri üretilebilmeli.
    assert open_bytes(dst.read_bytes(), passphrase) == payload


def test_seal_file_keeps_original_when_not_asked(tmp_path):
    """Varsayılan davranış: kaynağa dokunma."""
    _needs_crypto()
    src = tmp_path / "bundle"
    src.write_bytes(_secret_ish())
    dst = tmp_path / "bundle.sealed"

    info = seal_file(src, dst, os.urandom(24).hex(), delete_original=False)

    assert info["deleted"] is False
    assert src.exists()


def test_main_seal_refuses_to_overwrite(tmp_path, monkeypatch):
    """Var olan bir .sealed dosyasının üzerine yazmak mührü kaybettirebilir."""
    _needs_crypto()
    src = tmp_path / "a.bin"
    src.write_bytes(_secret_ish())
    dst = tmp_path / "a.bin.sealed"
    dst.write_bytes(b"dokunma")
    monkeypatch.setenv("SEAL_TEST_KEY", os.urandom(24).hex())

    code = main(["--path", str(src), "--seal", "--passphrase-env", "SEAL_TEST_KEY"])

    assert code == 2
    assert dst.read_bytes() == b"dokunma"


def test_main_requires_exactly_one_mode(tmp_path):
    """`--seal` ve `--open` birlikte verilirse hangisinin kazandığı belirsiz."""
    _needs_crypto()
    src = tmp_path / "a.bin"
    src.write_bytes(b"x")

    assert main(["--path", str(src)]) == 2
    assert main(["--path", str(src), "--seal", "--open"]) == 2


def test_main_open_roundtrip(tmp_path, monkeypatch):
    """CLI'nin uçtan uca yolu: mühürle -> aç -> aynı baytlar."""
    _needs_crypto()
    src = tmp_path / "yedek.bundle"
    payload = _secret_ish() * 20
    src.write_bytes(payload)
    monkeypatch.setenv("SEAL_TEST_KEY", os.urandom(24).hex())

    assert main(["--path", str(src), "--seal", "--passphrase-env", "SEAL_TEST_KEY"]) == 0
    sealed = tmp_path / "yedek.bundle.sealed"
    assert sealed.exists()

    out = tmp_path / "geri-donus.bundle"
    code = main(["--path", str(sealed), "--open", "--passphrase-env",
                 "SEAL_TEST_KEY", "--out", str(out)])

    assert code == 0
    assert out.read_bytes() == payload


def test_main_open_wrong_key_exit_code_1(tmp_path, monkeypatch):
    """Yanlış parola çıkış kodu 1 — 0 ile karışırsa otomasyon 'oldu' sanır."""
    _needs_crypto()
    src = tmp_path / "a.bin"
    src.write_bytes(_secret_ish())
    monkeypatch.setenv("SEAL_GOOD", os.urandom(24).hex())
    monkeypatch.setenv("SEAL_BAD", os.urandom(24).hex())

    assert main(["--path", str(src), "--seal", "--passphrase-env", "SEAL_GOOD"]) == 0
    code = main(["--path", str(tmp_path / "a.bin.sealed"), "--open",
                 "--passphrase-env", "SEAL_BAD", "--out", str(tmp_path / "out.bin")])

    assert code == 1
    assert not (tmp_path / "out.bin").exists()

    """Boş parola = parolasız arşiv. Reddedilmeli, uyarıyla geçilmemeli."""
    _needs_crypto()
    with pytest.raises(ValueError, match="boş parola"):
        seal_bytes(_secret_ish(), "")


def test_not_a_sealed_file_rejected():
    """Düz bir dosyayı 'mühürlü' sanıp açmaya çalışmak sessiz geçmemeli."""
    _needs_crypto()
    with pytest.raises(ValueError, match="MAGIC yok"):
        open_bytes(b"just a normal tarball, nothing sealed here", "x")
