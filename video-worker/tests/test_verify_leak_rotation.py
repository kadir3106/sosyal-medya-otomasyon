"""Döndürme doğrulayıcısı — çözüyor mu, doğru hüküm veriyor mu?

Bu betiğin tek işi "sır hâlâ geçerli mi" sorusunu **ölçmek**. Yanlış hüküm
verirse ya yapılmamış bir döndürmeyi "tamam" sayar (tehlikeli) ya da
yapılmışı "açık" gösterir (gürültü). Bu yüzden çözme yolu gerçek bir
şifreleme turuyla test ediliyor: n8n'in `CipherAes256CBC.encrypt`'i
burada yeniden üretilip `decrypt_n8n` ile geri açılıyor.

Sırlar literal yazılmıyor — dosya izlenen bir dosya, tarayıcı kendi
fixture'ını bulgu olarak raporlamasın (bkz. test_secret_scan.py).
"""
import base64
import hashlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from verify_leak_rotation import (  # noqa: E402
    MAGIC,
    TIKTOK_PROFILE,
    check_n8n_password,
    check_telegram,
    check_tiktok,
    decrypt_n8n,
    fp,
    read_env,
)


def _needs_crypto():
    """`cryptography` CI'da `requirements.txt` içinde YOK — test atlanmalı, düşmemeli.

    `scripts/verify_leak_rotation.py` bunu tembel import ediyor, ama şifreleme
    turu testi gerçek AES ister. Atlama sessiz olmadığı için (skipped sayısı
    görünür) körlük üretmez.
    """
    pytest.importorskip("cryptography.hazmat.primitives.ciphers")


def _encrypt_like_n8n(plaintext: str, key: str, salt: bytes = b"12345678") -> str:
    """n8n `CipherAes256CBC.encrypt` — testin referans uygulaması.

    Node'un `cipher.update()`'u PKCS7 padding'i **otomatik** ekler; Python'un
    `cryptography` paketi eklemez. Burada elle ekleniyor, yoksa blok hizalama
    hatası alınır (ölçüldü: ilk denemede tam bu oldu).
    """
    _needs_crypto()
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    password = key.encode("latin-1") + salt
    h1 = hashlib.md5(password).digest()
    h2 = hashlib.md5(h1 + password).digest()
    derived_key = h1 + h2
    iv = hashlib.md5(h2 + password).digest()

    raw = plaintext.encode()
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad

    encryptor = Cipher(algorithms.AES(derived_key), modes.CBC(iv)).encryptor()
    body = encryptor.update(raw) + encryptor.finalize()
    return base64.b64encode(MAGIC + salt + body).decode()


def test_fingerprint_is_stable_and_not_the_secret():
    value = "".join(["test", "value", "123"])
    assert fp(value) == fp(value)
    assert len(fp(value)) == 8
    assert value not in fp(value)


def test_roundtrip_matches_n8n_format():
    fake_key = "k" * 32
    payload = '{"accessToken": "' + "t" * 46 + '"}'
    cipher = _encrypt_like_n8n(payload, fake_key)
    assert decrypt_n8n(cipher, fake_key) == payload


def test_decrypt_rejects_foreign_format():
    """Base64 ama n8n değil: sessizce çöp döndürmek yerine hata vermeli."""
    _needs_crypto()

    import json as _json

    plain_b64 = base64.b64encode(_json.dumps({"a": "b"}).encode()).decode()
    with pytest.raises(ValueError, match="Salted__"):
        decrypt_n8n(plain_b64, "k" * 32)


def test_decrypt_rejects_wrong_key():
    """Yanlış anahtar padding kontrolünde yakalanmalı, çöp döndürmemeli."""
    _needs_crypto()

    cipher = _encrypt_like_n8n("gizli-icerik", "a" * 32)
    with pytest.raises(ValueError):
        decrypt_n8n(cipher, "b" * 32)


def test_read_env_handles_bom(tmp_path, monkeypatch):
    """BOM'lu `.env` ilk anahtarı gizlememeli — ilk ölçümde tam bu olmuştu."""
    import verify_leak_rotation as mod

    env_file = tmp_path / ".env"
    env_file.write_bytes(b"\xef\xbb\xbfTELEGRAM_BOT_TOKEN=abc\nN8N_PASSWORD=pw\n")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    parsed = mod.read_env()
    assert parsed["TELEGRAM_BOT_TOKEN"] == "abc"
    assert parsed["N8N_PASSWORD"] == "pw"


def test_check_telegram_flags_leaked_token(monkeypatch):
    """Sızan token canlıysa 'HALA GECERLI', 401 ise 'iptal' hükmü verilmeli.

    Ağa çıkılmıyor: `urlopen` sahte. Asıl önemli olan, **hangi token'ın**
    sorgulandığı — sızan ile `.env`'deki karışırsa yanlış bot iptal edilir.
    """
    import verify_leak_rotation as mod

    fake_key = "k" * 32
    leaked = "9" * 46
    current = "8" * 46
    seen: list[str] = []

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true, "result": {"username": "leaked_bot"}}'

    def fake_urlopen(url, timeout=15):
        seen.append(url)
        return _Resp()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        mod, "decrypt_n8n",
        lambda data, key: '{"accessToken": "%s"}' % leaked)

    creds = [{"type": "telegramApi", "data": "x"}]
    lines = mod.check_telegram(fake_key, creds, {"TELEGRAM_BOT_TOKEN": current})

    assert any("HALA GECERLI" in line for line in lines)
    assert any("aynı mı: False" in line for line in lines)
    # Sızan token 401 verirse "iptal edilmiş" denmeli.
    assert leaked in seen[0] and current in seen[1]


def test_check_telegram_reports_revoked_token(monkeypatch):
    """Döndürme başarılıysa (HTTP 401) betik bunu 'iptal' olarak raporlamalı."""
    import urllib.error

    import verify_leak_rotation as mod

    def fake_urlopen(url, timeout=15):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod, "decrypt_n8n", lambda data, key: '{"accessToken": "abc"}')

    lines = mod.check_telegram("k" * 32, [{"type": "telegramApi", "data": "x"}],
                               {"TELEGRAM_BOT_TOKEN": ""})
    assert not any("HALA GECERLI" in line for line in lines)
    assert any("HTTP 401" in line for line in lines)


def test_check_n8n_password_detects_unchanged_password(monkeypatch):
    """Arşivdeki hash mevcut parolayla açılıyorsa açıkça söylenmeli."""
    bcrypt = __import__("pytest").importorskip("bcrypt")

    stored = bcrypt.hashpw(b"mevcut-parola", bcrypt.gensalt()).decode()
    lines = check_n8n_password({"email": "a@b.c", "password": stored},
                               {"N8N_PASSWORD": "mevcut-parola"})
    assert any("HALA AYNI" in line for line in lines)

    lines = check_n8n_password({"email": "a@b.c", "password": stored},
                               {"N8N_PASSWORD": "farkli-parola"})
    assert not any("HALA AYNI" in line for line in lines)


def test_check_tiktok_reports_missing_profile(tmp_path, monkeypatch):
    import verify_leak_rotation as mod

    monkeypatch.setattr(mod, "TIKTOK_PROFILE", tmp_path / "yok")
    lines = mod.check_tiktok()
    assert any("silinmiş" in line for line in lines)


def test_main_exit_codes(monkeypatch):
    """0 = her şey etkisiz, 1 = açık var, 2 = ölçülemedi."""
    import verify_leak_rotation as mod

    monkeypatch.setattr(mod, "read_env", lambda: {})
    monkeypatch.setattr(mod, "load_n8n_store", lambda: ("k" * 32, [], {}))
    monkeypatch.setattr(mod, "check_telegram", lambda *a: ["SIZAN : HTTP 401 iptal"])
    monkeypatch.setattr(mod, "check_n8n_password", lambda *a: ["SONUC : değişmiş"])
    monkeypatch.setattr(mod, "check_tiktok", lambda: ["profil silinmiş"])
    # Disk gerçekten okunursa test bu makinenin yedeklerine bağlı kalır ve
    # yedek silindiği gün yeşilden kırmızıya döner — ölçüm değil, ortam bağımlılığı.
    monkeypatch.setattr(mod, "check_stray_copies", lambda: ["yedek.bundle yok — ✅"])
    assert mod.main([]) == 0

    monkeypatch.setattr(mod, "check_telegram", lambda *a: ["SIZAN : HTTP 200  >>> HALA GECERLI <<<"])
    assert mod.main([]) == 1


def test_main_returns_2_when_archive_missing(monkeypatch):
    import verify_leak_rotation as mod

    def boom():
        raise FileNotFoundError("arşiv yok")

    monkeypatch.setattr(mod, "read_env", lambda: {})
    monkeypatch.setattr(mod, "load_n8n_store", boom)
    assert mod.main([]) == 2


def test_failure_output_names_panel_and_says_not_automatable(monkeypatch, capsys):
    """Açık kalem varken çıktı, paneli ve "otomatik: HAYIR" hükmünü göstermeli.

    Neden: bir sonraki turda "bunu betikle yapabilir miyiz" sorusu yeniden
    sorulmasın. Hüküm ölçülmüş (Bölüm 2.1c), tahmin değil.
    """
    import verify_leak_rotation as mod

    monkeypatch.setattr(mod, "read_env", lambda: {})
    monkeypatch.setattr(mod, "load_n8n_store", lambda: ("k" * 32, [], {}))
    monkeypatch.setattr(mod, "check_telegram",
                        lambda *a: ["SIZAN : HTTP 200  >>> HALA GECERLI <<<"])
    monkeypatch.setattr(mod, "check_n8n_password", lambda *a: ["SONUC : HALA AYNI"])
    monkeypatch.setattr(mod, "check_tiktok", lambda: ["profil : HALA DISKTE"])
    monkeypatch.setattr(mod, "check_stray_copies", lambda: ["HALA DISKTE   : yedek.bundle"])

    assert mod.main([]) == 1
    out = capsys.readouterr().out
    assert "BETİKLE YAPILAMAZ" in out
    for panel in ("BotFather", "n8n UI", "Mobil uygulama"):
        assert panel in out
    assert out.count("otomatik: HAYIR") == 4


def test_stray_copy_detected_even_outside_repo(tmp_path, monkeypatch):
    """Repo dışındaki yedek kopya da "açık kalem" sayılmalı.

    Neden: `.gitignore` `*.tar.gz` ve `*.bundle` desenlerini yok sayıyor, yani
    `secret_scan --history` de HEAD taraması da onları hiç görmüyor. Ölçüm
    (2026-11-02): diskteki 130 MB'lık bundle'da tiktok_session profili (941
    nesne) ve süresi 2027-03-16'ya kadar geçerli `sessionid` çerezi duruyor.
    Tarayıcı "temiz" derken sır okunabilir bir kopyada yaşıyordu.
    """
    import verify_leak_rotation as mod

    inside = tmp_path / "backups" / "yedek.tar.gz"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"x")
    outside = tmp_path.parent / "repo-YEDEK.bundle"
    outside.write_bytes(b"x")
    monkeypatch.setattr(mod, "LEAK_COPIES", [
        (outside, "git bundle"),
        (inside, "n8n yedegi"),
    ])

    lines = mod.check_stray_copies()
    text = "\n".join(lines)
    assert len([ln for ln in lines if ln.startswith("HALA DISKTE")]) == 2
    assert "repo-YEDEK.bundle" in text


def test_stray_copy_absent_is_not_a_failure(tmp_path, monkeypatch):
    """Silinmiş kopya açık kalem değil — ✅ ile raporlanmalı."""
    import verify_leak_rotation as mod

    monkeypatch.setattr(mod, "LEAK_COPIES", [(tmp_path / "yok.bundle", "git bundle")])
    lines = mod.check_stray_copies()
    assert not any("HALA DISKTE" in line for line in lines)
    assert any("yok" in line for line in lines)

def test_sealed_copy_counts_as_closed(tmp_path, monkeypatch):
    """Mühürlü kopya AÇIK kalem değil — yoksa uyarı hiç bitmez.

    Mühürleme AES-256-GCM ile sır okunamaz hale getiriyor; bunu "hâlâ diskte"
    diye raporlayan bir doğrulayıcı operatörü yorar ve asıl uyarıyı
    (döndürme yapılmadı) gürültüye boğar.
    """
    import verify_leak_rotation as mod

    src = tmp_path / "yedek.bundle"
    sealed = tmp_path / "yedek.bundle.sealed"
    sealed.write_bytes(b"LEAKSEAL...muhurlu...")
    monkeypatch.setattr(mod, "LEAK_COPIES", [(src, "git bundle")])

    lines = mod.check_stray_copies()
    text = "\n".join(lines)

    assert "HALA DISKTE" not in text
    assert "MÜHÜRLÜ" in text
    assert "✅" in text


def test_sealed_plus_plain_still_warns(tmp_path, monkeypatch):
    """Mühürleme tek başına yetmez: düz kopya duruyorsa sır hâlâ okunabilir.

    Bu senaryo gerçek bir tuzak: `--seal` çalıştırılıp `--delete-originals`
    unutulursa hem .sealed hem kaynak kalır. "Mühürlü var" diye ✅ vermek
    yanlış olurdu.
    """
    import verify_leak_rotation as mod

    src = tmp_path / "yedek.bundle"
    src.write_bytes(b"x")
    (tmp_path / "yedek.bundle.sealed").write_bytes(b"LEAKSEAL...")
    monkeypatch.setattr(mod, "LEAK_COPIES", [(src, "git bundle")])

    lines = mod.check_stray_copies()
    text = "\n".join(lines)

    assert "HALA DISKTE" in text
    assert "DÜZ kopya" in text


def test_stray_message_points_to_seal_command(tmp_path, monkeypatch):
    """Uyarı çözümü de söylemeli — yoksa operatör silmeye gider ve geçmişi kaybeder."""
    import verify_leak_rotation as mod

    src = tmp_path / "yedek.bundle"
    src.write_bytes(b"x")
    monkeypatch.setattr(mod, "LEAK_COPIES", [(src, "git bundle")])

    text = "\n".join(mod.check_stray_copies())

    assert "seal_leak_copies.py" in text
    assert "delete-originals" in text




def test_capabilities_cover_every_failure_key():
    """Her olası açık kalem için bir yetenek satırı olmalı (sessiz boşluk olmasın)."""
    import verify_leak_rotation as mod

    names = {row[0] for row in mod.CAPABILITIES}
    assert names == {"telegram", "n8n-parola", "tiktok", "yedek-kopya"}
    for name, panel, auto, why in mod.CAPABILITIES:
        assert panel and auto == "HAYIR" and len(why) > 20


def test_tiktok_verdict_says_web_cannot_revoke(tmp_path, monkeypatch):
    """TikTok hükmü, iptalin web'de olmadığını yazmalı — yanlış yönlendirme olmasın."""
    import sqlite3

    import verify_leak_rotation as mod

    profile = tmp_path / "tiktok_session"
    net = profile / "Default" / "Network"
    net.mkdir(parents=True)
    con = sqlite3.connect(str(net / "Cookies"))
    con.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, expires_utc INTEGER)")
    con.execute("INSERT INTO cookies VALUES ('.tiktok.com','sessionid',13350000000000000)")
    con.commit()
    con.close()

    monkeypatch.setattr(mod, "TIKTOK_PROFILE", profile)
    lines = mod.check_tiktok()
    assert any("HALA DISKTE" in line for line in lines)
    assert any("web ayarlarında" in line and "YOK" in line for line in lines)
