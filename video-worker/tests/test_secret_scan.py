"""Sır tarayıcısının kendisi — yakalıyor mu, yanlış alarm veriyor mu?

Bir tarayıcı "temiz" dediğinde bunun bir anlamı olması için hem gerçek sırları
yakalaması hem de yer tutucuları/örnekleri yok sayması gerekir. Ölçülen gerçek
durum: 385 izlenen dosyada bulgu yok; bu testler tarayıcının kör olmadığını
kanıtlıyor.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from secret_scan import main as scan_main  # noqa: E402
from secret_scan import scan_text  # noqa: E402


def test_detects_openai_style_key():
    hits = scan_text('OPENAI_API_KEY = "sk-abcdefghijklmnopqrstuvwx"')
    assert [h[0] for h in hits] == ["openai_key"]


def test_detects_groq_key():
    hits = scan_text('GROQ_API_KEY="gsk_abcdefghijklmnopqrstuvwx"')
    assert any(h[0] == "groq_key" for h in hits)


def test_detects_telegram_bot_token():
    hits = scan_text('TELEGRAM_BOT_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"')
    assert any(h[0] == "telegram_bot_token" for h in hits)


def test_detects_private_key_block():
    hits = scan_text("-----BEGIN RSA PRIVATE KEY-----")
    assert any(h[0] == "private_key" for h in hits)


def test_detects_assigned_long_secret():
    hits = scan_text('META_ACCESS_TOKEN="EAAGabcdefghijklmnopqrstuvwxyz123456"')
    assert any(h[0] == "assigned_secret" for h in hits)


def test_ignores_placeholders_and_examples():
    for line in (
        'OPENAI_API_KEY="sk-your_key_here_placeholder"',
        'TOKEN = "${TOKEN}"',
        'SECRET = "<changeme>"',
        'API_KEY = "example_example_example_example"',
        'token = "dummy_dummy_dummy_dummy_dummy"',
    ):
        assert scan_text(line) == [], line


def test_does_not_leak_the_secret_in_findings():
    """Bulgu raporu sırrı tekrar yazmamalı (CI log'u herkese açık olabilir)."""
    hits = scan_text('X_TOKEN="supersecretvalue1234567890abcd"')
    assert hits
    snippet = hits[0][2]
    assert "supersecretvalue" not in snippet


def test_repo_itself_is_clean():
    """Depoda bilinen sır olmamalı — CI'daki kapının aynısı."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "secret_scan.py"), str(repo_root)],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout


def test_main_returns_nonzero_on_finding(tmp_path, monkeypatch):
    """`main` gerçekten 1 döndürmeli — CI adımı buna bakıyor."""
    import secret_scan

    monkeypatch.setattr(secret_scan, "tracked_files", lambda: [Path("leak.py")])
    (tmp_path / "leak.py").write_text('KEY = "sk-abcdefghijklmnopqrstuvwx"', encoding="utf-8")

    assert scan_main([str(tmp_path)]) == 1
