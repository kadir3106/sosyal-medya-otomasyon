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
    scan_text,
    scan_text_values,
)

# Test fixture'ları dinamik kuruluyor: literal sır yazılsaydı tarayıcı bu dosyayı
# da bulgu sayardı (test_secret_scan.py'de aynı gerekçe ölçülmüştü).
_RANDOM = "abcdefghijklmnopqrstuvwxyz0123456789"


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


def test_untracked_files_are_scanned(tmp_path, monkeypatch):
    """Commit edilmemiş dosya da taranmalı — commit ÖNCESİ kapı olması için.

    Ölçüm: `tracked_files()` = `git ls-files` yalnızca izlenen dosyaları
    döndürüyordu. Bu dosyaya sır desenine uyan bir literal koydum, yerel
    tarama "Temiz" dedi, commit edip CI'a gidince hem `test` hem
    `history-scan` kırıldı. Hata commit'ten SONRA ortaya çıktı.
    """
    # Gerçek depoda gerçekten izlenmeyen bir dosya üret ve hedef listesinde
    # göründüğünü doğrula. `main` çağırmıyoruz: o tüm depoyu tarar ve başka
    # testlerle yarışır.
    repo = Path(__file__).resolve().parent.parent.parent
    probe = repo / "_scan_probe_untracked.py"
    try:
        probe.write_text("KEY = 1\n", encoding="utf-8")
        names = {p.as_posix() for p in secret_scan.scan_targets(repo)}
        assert "_scan_probe_untracked.py" in names, (
            "izlenmeyen dosya hedef listesinde olmalı; aksi halde tarayıcı "
            "commit öncesi kör kalır"
        )
    finally:
        probe.unlink(missing_ok=True)


# --- İçerik taraması: tam değer, maskeli rapor ----------------------------

def test_scan_text_values_returns_full_value_but_masks_report():
    secret = "sk-" + "qwertyuiopasdfghjklzxcvb"
    hits = scan_text_values(f'KEY = "{secret}"')
    assert hits, "desen eşleşmeli"
    name, lineno, full, masked = hits[0]
    assert full == secret          # HEAD karşılaştırması tam değer ister
    assert secret not in masked    # rapor sırrı sızdırmamalı


def test_sequential_run_marks_synthetic_key():
    """Sıralı alfabeden kurulmuş sahte anahtar işaretlenir."""
    sequential = "sk-" + "abcde" + "fghij" + "klmno" + "pqrstuvwx"
    random_like = "sk-" + "qwertyuiop" + "asdfghjkl" + "zxcvb"
    assert secret_scan._sequential_run(sequential)
    assert not secret_scan._sequential_run(random_like)


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


# --- Arşiv kör noktası (madde 29.7) ---------------------------------------
#
# Ölçüm (2026-11-02): geçmişte `backups/otomasyon-yedek-2026-09-05.tar.gz`
# vardı. `iter_history_texts` ikili blob'ları (gzip `\x00` içerir) sessizce
# atladığı için tarayıcı onu hiç görmedi ve "geçmişte yeni sır yok" dedi.
# `.zip` ayrıca `SKIP_SUFFIXES`'teydi, yani HEAD taramasında da görünmezdi.

def test_path_detector_flags_archives():
    """Arşivin kendisi bulgudur — içeriği açılamasa bile."""
    names = [h[0] for h in scan_path("backups/otomasyon-yedek-2026-09-05.tar.gz")]
    assert "archive_file" in names
    assert "archive_file" in [h[0] for h in scan_path("dump.zip")]
    assert "archive_file" in [h[0] for h in scan_path("a/b/state.tgz")]


def test_path_is_archive_matches_detector():
    """`path_is_archive` ile dedektör aynı listeyi kullanmalı.

    İkisi ayrışırsa içerik taraması açılır ama yol bulgusu üretilmez (veya
    tersi) — kör nokta sessizce geri gelir.
    """
    for name in ("x.tar.gz", "x.zip", "x.7z", "x.tar.bz2", "x.txz"):
        assert secret_scan.path_is_archive(name), name
        assert "archive_file" in [h[0] for h in scan_path(name)], name
    for name in ("x.py", "x.json", "x.gz.txt", "arşiv/notlar"):
        assert not secret_scan.path_is_archive(name), name


def _tar_gz(members: dict[str, bytes]) -> bytes:
    """Bellek içi .tar.gz üretir."""
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def test_archive_contents_are_actually_read():
    """Tarball içindeki sır, gzip'li olmasına rağmen bulunmalı.

    Bu, düzeltmenin kalbi: `read_archive_texts` açmazsa tarayıcı yine kördür.
    """
    data = _tar_gz({"app/.env": b'OPENAI_API_KEY="sk-' + b"A" * 30 + b'"\n'})
    texts = secret_scan.read_archive_texts("backups/yedek.tar.gz", data)
    assert texts, "arşiv açılmadı"
    values = [v for _, text in texts for _, _, v, _ in scan_text_values(text)]
    assert any(v.startswith("sk-") for v in values)


def test_zip_archive_contents_are_read():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config.py", 'GROQ_API_KEY="gsk_' + "B" * 30 + '"\n')
    texts = secret_scan.read_archive_texts("dump.zip", buf.getvalue())
    assert any("gsk_" in text for _, text in texts)


def test_broken_archive_does_not_crash_and_still_flags_path():
    """Bozuk arşiv istisna fırlatmamalı — ama yol bulgusu yine üretilmeli.

    "Açamadım" asla "temiz" anlamına gelmemeli.
    """
    assert secret_scan.read_archive_texts("bozuk.tar.gz", b"not an archive") == []
    assert "archive_file" in [h[0] for h in scan_path("bozuk.tar.gz")]


def test_nested_archive_is_opened():
    """Arşiv içindeki arşiv de açılmalı.

    Ölçülen gerçek durum: `backups/otomasyon-yedek-*.tar.gz` → `n8n-data.tar`
    → `./config` (n8n encryptionKey). İlk sürüm iç arşivi "ikili" diye atlıyor
    ve dosya içindeki sırrı hiç görmüyordu.
    """
    inner = _tar_gz({"config": b'{"encryptionKey":"%s"}' % _RANDOM[:32].encode()})
    outer = _tar_gz({"n8n-data.tar": inner})

    texts = secret_scan.read_archive_texts("backups/yedek.tar.gz", outer)
    joined = "\n".join(text for _, text in texts)

    assert "encryptionKey" in joined, "iç arşiv açılmadı"
    # Üye yolu iki katmanı da göstermeli: hangi dosyada olduğu kaybolmasın.
    assert any(path.count("!") == 2 for path, _ in texts)


def test_json_secret_field_is_detected():
    """JSON alanındaki sır yakalanmalı (`KEY = "..."` biçimi değil)."""
    key = _RANDOM[:32]
    hits = scan_text('{"encryptionKey":"%s"}' % key)
    assert [h[0] for h in hits] == ["json_secret_field"]


def test_json_secret_field_ignores_short_and_sentinel_values():
    """Kısa değer ve "yazılmamalı" işareti bulgu değil."""
    assert scan_text('{"api_key":"short"}') == []
    assert scan_text('{"access_token":"should-not-be-written"}') == []


def test_deeply_nested_archive_is_reported_not_silently_skipped():
    """Derinlik sınırı aşılırsa sessizce geçilmez — açılamayan arşiv bildirilir.

    "Derine inmedim" bilgisi operatöre ulaşmazsa tarayıcı yine kördür; bu,
    düzeltmeye çalıştığımız hatanın ta kendisi olurdu.
    """
    payload = _tar_gz({"x.txt": b"merhaba"})
    # Sınırın bir fazlası katman: en dış + (MAX_ARCHIVE_DEPTH) iç içe.
    for _ in range(secret_scan.MAX_ARCHIVE_DEPTH):
        payload = _tar_gz({"inner.tar.gz": payload})

    secret_scan.reset_unopened_archives()
    secret_scan.read_archive_texts("dis.tar.gz", payload)

    assert secret_scan.unopened_archives(), "derin arşiv sessizce atlandı"
    path, depth = secret_scan.unopened_archives()[0]
    assert depth >= secret_scan.MAX_ARCHIVE_DEPTH
    assert path.startswith("dis.tar.gz!")



def test_history_scan_opens_archives(monkeypatch, capsys):
    """`--history` arşivleri açarak taramalı.

    `include_archives=False` kalsaydı `backups/*.tar.gz` sınıfı yine görünmezdi.
    """
    data = _tar_gz({"app/.env": b'OPENAI_API_KEY="sk-' + b"C" * 30 + b'"\n'})
    captured: dict[str, bool] = {}

    def fake_iter(pairs, *, max_bytes=2_000_000, include_archives=False):
        captured["include_archives"] = include_archives
        return []

    monkeypatch.setattr(secret_scan, "history_objects", lambda: [("sha", "backups/x.tar.gz")])
    monkeypatch.setattr(secret_scan, "iter_history_texts", fake_iter)
    monkeypatch.setattr(secret_scan, "_head_texts", lambda paths: {})
    monkeypatch.setattr(secret_scan, "load_baseline", lambda *a, **k: set())

    found, _counts = secret_scan.scan_history_struct()
    assert captured["include_archives"] is True, "geçmiş taraması arşivleri açmıyor"
    # Yol bulgusu arşivden bağımsız olarak üretilmeli.
    assert any("backups/x.tar.gz" == f["path"] for f in found)
    assert data  # üretilen arşiv kullanıldı (regresyon amaçlı referans)
