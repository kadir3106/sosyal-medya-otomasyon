"""İzlenen dosyalarda sır/credential deseni tarar.

Neden gerekli: yerel `.env`'de 23 kimliğin 14'ü canlıydı ve testler bu yüzden
gerçek API'lere çıkıyordu (madde 20). `.env` ignore'lu ama bir gün biri
`config.py` içine token yapıştırırsa kimse fark etmez. Bu betik CI'da izlenen
dosyaları tarar.

Kullanım:
    python scripts/secret_scan.py            # 0 = temiz, 1 = bulgu var
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# (ad, desen) — desenler gerçek sırların biçimine bakar, anahtar adına değil.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("groq_key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9_-]{30,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    # Uzun rastgele sır ataması: TOKEN=..., SECRET=..., KEY=... (yer tutucular hariç)
    (
        "assigned_secret",
        re.compile(
            r"""(?i)\b\w*(?:secret|token|api_key|apikey|password)\w*\s*=\s*"""
            r"""["']([A-Za-z0-9_\-]{24,})["']"""
        ),
    ),
]

# Bu değerler gerçek sır değil; desen eşleşse de yok sayılır.
ALLOWLIST_SUBSTRINGS = (
    "example", "placeholder", "your_", "xxx", "dummy", "fake", "test",
    "changeme", "redacted", "[", "]", "<", ">", "${",
)

# Üretilmiş/ikili içerik ve test fixture'ları taranmaz.
SKIP_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".mp4", ".mp3", ".wav", ".webp", ".gif",
    ".db", ".lock", ".ico", ".zip", ".patch", ".pdf",
)
SKIP_DIR_PARTS = ("video-output", "node_modules", ".git", "__pycache__", "_tmp")


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def scan_text(text: str) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            value = m.group(0)
            lowered = value.lower()
            if any(tok in lowered for tok in ALLOWLIST_SUBSTRINGS):
                continue
            # Satır başına tek bulgu: desenler en özelden en gene sıralı, yani
            # `sk-...` hem `openai_key` hem `assigned_secret` ile eşleşse de
            # operatöre tek satır rapor edilir.
            hits.append((name, lineno, value[:6] + "…"))
            break
    return hits


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(args[0]) if args else Path.cwd()

    findings: list[str] = []
    for path in tracked_files():
        rel = path.as_posix()
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in path.parts for part in SKIP_DIR_PARTS):
            continue
        full = root / path
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, lineno, snippet in scan_text(text):
            findings.append(f"{rel}:{lineno}: {name} ({snippet})")

    if findings:
        print("Olası sır bulundu:")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"Temiz: {len(tracked_files())} izlenen dosyada sır deseni bulunamadı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
