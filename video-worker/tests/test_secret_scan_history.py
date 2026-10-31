"""Geçmiş taraması — hangi sınıf sızıntıyı yakalıyor, hangisini kaçırıyor?

Bu dosyanın varlık nedeni ölçülmüş bir kör nokta: `video-output/tiktok_session/`
altında 1015 dosya (Cookies, Login Data, Local State) git geçmişindeydi ve
tarayıcı "Temiz: 394 dosyada sır deseni bulunamadı" diyordu. İki nedenle:
  1. `tracked_files()` = `git ls-files` -> geçmiş hiç taranmıyordu.
  2. `SKIP_DIR_PARTS` içinde `video-output` vardı -> bugün de 88 izlenen dosya
     orada ve görünmüyordu.
  3. Chromium `Cookies`/`Login Data` SQLite'tır (ikili) -> içerik regex'i asla
     eşleşmez. Bu sınıf için doğru dedektör YOL desenidir.

Testler hem körlüğü hem de yanlış alarmı iki yönde sabitler.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import secret_scan  # noqa: E402
from secret_scan import (  # noqa: E402
    finding_key,
    load_baseline,
    scan_path,
    scan_text_values,
)


# --- Yol tabanlı dedektör: tarayıcı oturum dosyaları -----------------------

def test_detects_chromium_cookie_store():
    """Gerçek sızıntıdaki yol: video-output/tiktok_session/Default/Network/Cookies."""
    hits = scan_path("video-output/tiktok_session/Default/Network/Cookies")
    names = [h[0] for h in hits]
    assert "browser_cookies" in names
    assert "browser_profile_dir" in names


def test_detects_login_data_and_local_state():
    login = [h[0] for h in scan_path("x/tiktok_session/Default/Login Data")]
    state = [h[0] for h in scan_path("x/tiktok_session/Local State")]
    assert "browser_login_data" in login
    assert "browser_local_state" in state


def test_detects_key_material_and_env():
    assert "ssh_private_key" in [h[0] for h in scan_path("home/id_rsa")]
    assert "key_material" in [h[0] for h in scan_path("certs/server.pem")]
    assert "dotenv" in [h[0] for h in scan_path("app/.env")]


def test_detects_dotenv_variants_not_just_exact_name():
    """`prod.env`, `app.env` de sırdır.

    Ölçüm: ilk desen `(^|/)\\.env$` idi, yani yalnızca tam `.env`. Uçtan uca
    testte geçici depoya eklenen `prod.env` KAÇIRILDI (çıkış 0 döndü).
    """
    for path in ("prod.env", "config/app.env", "deploy/prod.env"):
        assert "dotenv" in [h[0] for h in scan_path(path)], path


def test_does_not_flag_templates():
    """Şablon dosyaları sır taşımaz; sürekli kırmızı CI işe yaramaz."""
    for safe in (".env.example", "config.sample.env", "settings.template.pem"):
        assert scan_path(safe) == [], safe


def test_does_not_flag_ordinary_source_files():
    for safe in ("app/config.py", "docs/README.md", "tests/test_x.py"):
        assert scan_path(safe) == [], safe


# --- Kapsam: video-output artık atlanmıyor --------------------------------

def test_video_output_is_not_skipped():
    """Ölçülen kör nokta: hem ağaçta hem geçmişte taranmalı."""
    assert "video-output" not in secret_scan.SKIP_DIR_PARTS


# --- İçerik taraması: tam değer, maskeli rapor ----------------------------

def test_scan_text_values_returns_full_value_but_masks_report():
    secret = "sk-" + "qwertyuiopasdfghjklzxcvb"
    hits = scan_text_values(f'KEY = "{secret}"')
    assert hits, "desen eşleşmeli"
    name, lineno, full, masked = hits[0]
    assert full == secret          # HEAD karşılaştırması tam değer ister
    assert secret not in masked    # rapor sırrı sızdırmamalı


def test_sequential_placeholder_is_marked_not_suppressed():
    """`sk-abcdefghij...` sahtedir ama susturulmuyor, işaretleniyor."""
    assert secret_scan._sequential_run("sk-abcdefghijklmnopqrstuvwx")
    assert not secret_scan._sequential_run("sk-qwertyuiopasdfghjklzxcvb")


# --- Baseline: yeni sızıntı kırmızı, bilinen kabul -------------------------

def test_finding_key_is_stable_across_platforms():
    key = finding_key("path", "browser_cookies", "a/b/../c")
    assert key.startswith("path:browser_cookies:")
    assert "\\" not in key


def test_finding_key_distinguishes_different_values_in_same_file():
    """Aynı dosyadaki FARKLI sır aynı anahtara düşmemeli.

    Ölçüm: anahtar (desen, dosya) iken `test_secret_scan.py` içindeki üç ayrı
    OpenAI değeri tek anahtar üretiyordu — aynı dosyaya yeni bir anahtar
    eklense baseline onu sessizce yutardı.
    """
    a = finding_key("content", "openai_key", "tests/t.py", "sk-" + "a" * 24)
    b = finding_key("content", "openai_key", "tests/t.py", "sk-" + "b" * 24)
    assert a != b
    assert a.startswith("content:openai_key:tests/t.py:")


def test_finding_key_does_not_embed_the_secret():
    """Baseline dosyası sırrın kendisini taşımamalı — yalnızca özet."""
    secret = "sk-" + "z9y8x7w6v5u4t3s2r1q0p9o8"
    key = finding_key("content", "openai_key", "tests/t.py", secret)
    assert secret not in key
    assert len(key.rsplit(":", 1)[1]) == 12


def test_baseline_file_is_valid_json():
    """Baseline okunamazsa CI sessizce her şeyi 'yeni' sayar."""
    path = secret_scan.BASELINE_PATH
    assert path.is_file(), "baseline üretilmeli: --history --update-baseline"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "accepted" in data
    assert all("key" in e for e in data["accepted"])


def test_load_baseline_reads_keys(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(
        json.dumps({"accepted": [{"key": "path:dotenv:app/.env"}]}), encoding="utf-8"
    )
    assert load_baseline(p) == {"path:dotenv:app/.env"}


def test_load_baseline_missing_file_is_empty(tmp_path):
    assert load_baseline(tmp_path / "yok.json") == set()


def test_known_leak_does_not_fail_but_new_one_does(monkeypatch, capsys):
    """Baseline'daki bulgu CI'ı kırmamalı; baseline'da olmayan kırmalı."""
    known = {
        "kind": "path", "detector": "browser_cookies",
        "path": "old/Cookies", "detail": "old/Cookies",
    }
    new = {
        "kind": "path", "detector": "browser_cookies",
        "path": "new/Cookies", "detail": "new/Cookies",
    }
    monkeypatch.setattr(
        secret_scan, "scan_history_struct",
        lambda: ([known, new], {"path_hits": 2, "content_hits": 0, "in_tree": 0}),
    )
    monkeypatch.setattr(
        secret_scan, "load_baseline",
        lambda *a, **k: {finding_key("path", "browser_cookies", "old/Cookies")},
    )
    rc = secret_scan.main(["--history"])
    out = capsys.readouterr().out
    assert rc == 1, "yeni sızıntı CI'ı kırmalı"
    assert "1 YENİ" in out
    assert "old/Cookies" not in out, "kabul edilmiş bulgu gürültü yapmamalı"
    assert "new/Cookies" in out


def test_all_baseline_findings_pass(monkeypatch, capsys):
    known = {
        "kind": "path", "detector": "browser_cookies",
        "path": "old/Cookies", "detail": "old/Cookies",
    }
    monkeypatch.setattr(
        secret_scan, "scan_history_struct",
        lambda: ([known], {"path_hits": 1, "content_hits": 0, "in_tree": 0}),
    )
    monkeypatch.setattr(
        secret_scan, "load_baseline",
        lambda *a, **k: {finding_key("path", "browser_cookies", "old/Cookies")},
    )
    assert secret_scan.main(["--history"]) == 0
