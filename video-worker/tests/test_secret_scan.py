"""Sır tarayıcısının kendisi — yakalıyor mu, yanlış alarm veriyor mu?

Bir tarayıcı "temiz" dediğinde bunun bir anlamı olması için hem gerçek sırları
yakalaması hem de yer tutucuları/örnekleri yok sayması gerekir. Ölçülen gerçek
durum: 385 izlenen dosyada bulgu yok; bu testler tarayıcının kör olmadığını
kanıtlıyor.

ÖNEMLİ: sahte sırlar burada **dinamik** kuruluyor, literal yazılmıyor. Dosya
izlenen bir dosya olduğu için literal yazılsaydı tarayıcı kendi test fixture'ını
sır olarak raporlardı (ölçüldü: tam paket 1 hata verdi). Parçalara bölmek hem
bunu önler hem de testin niyetini korur.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from secret_scan import main as scan_main  # noqa: E402
from secret_scan import scan_text  # noqa: E402

_RANDOM = "abcdefghijklmnopqrstuvwxyz0123456789"


def _fake(prefix: str, n: int = 24) -> str:
    """Desenle eşleşen ama bu dosyada literal olarak bulunmayan sahte sır."""
    return prefix + _RANDOM[:n]


def test_detects_openai_style_key():
    hits = scan_text(f'OPENAI_API_KEY = "{_fake("sk-")}"')
    assert [h[0] for h in hits] == ["openai_key"]


def test_detects_groq_key():
    hits = scan_text(f'GROQ_API_KEY="{_fake("gsk_")}"')
    assert any(h[0] == "groq_key" for h in hits)


def test_detects_telegram_bot_token():
    # Bot id 8-10 hane, iki nokta, en az 30 karakter: desenin tam sınırı.
    hits = scan_text(f'TELEGRAM_BOT_TOKEN = "{_fake("123456789:", 33)}"')
    assert any(h[0] == "telegram_bot_token" for h in hits)


def test_detects_private_key_block():
    marker = "-----BEGIN" + " RSA PRIVATE KEY-----"
    hits = scan_text(marker)
    assert any(h[0] == "private_key" for h in hits)


def test_detects_assigned_long_secret():
    # `EAAG` + 32 karakter: Meta token biçimi, uzun atama desenine düşer.
    hits = scan_text(f'META_ACCESS_TOKEN="{_fake("EAAG", 32)}"')
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
    secret = _fake("sk-")
    hits = scan_text(f'X_TOKEN="{secret}"')
    assert hits
    snippet = hits[0][2]
    assert secret not in snippet


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

    monkeypatch.setattr(secret_scan, "scan_targets", lambda *a, **k: [Path("leak.py")])
    (tmp_path / "leak.py").write_text(f'KEY = "{_fake("sk-")}"', encoding="utf-8")

    assert scan_main([str(tmp_path)]) == 1



def test_gitignore_covers_secret_carrying_backups():
    """Bundle ve mühürlü arşiv **depoya girmemeli**.

    Ölçüm (2026-11-02): bu bölüm önce `*.bundle` `.gitignore`'da diyordu ama
    `git check-ignore` "TAKİP EDİLEBİLİR" dedi. `*.sealed` hiç yoktu. Yani
    mühürleme yaptıktan sonra `git add .` o dosyayı sessizce commit'leyebilirdi
    — sır şifreli de olsa depoya yayılmış olurdu.

    Bu test `CAPABILITIES`'in kapsamadığı boşluğu kilitler: betik sır *değerini*
    arıyordu, sır *taşıyan dosyanın* depoya girebilir olmasını değil.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent

    for name in ("yedek.bundle", "yedek.bundle.sealed", "backups/a.tar.gz.sealed"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", name],
            cwd=str(repo_root),
        )
        assert result.returncode == 0, f"{name} .gitignore ile yok sayılmıyor"


def test_gitignore_keeps_backups_gitkeep():
    """`backups/*` geniş bir kural — `.gitkeep` istisnası korunmalı."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    result = subprocess.run(
        ["git", "check-ignore", "-q", "backups/.gitkeep"],
        cwd=str(repo_root),
    )
    assert result.returncode != 0, "backups/.gitkeep yok sayılmamalı (dizin boş kalır)"
