"""İzlenen dosyalarda sır/credential deseni tarar.

Neden gerekli: yerel `.env`'de 23 kimliğin 14'ü canlıydı ve testler bu yüzden
gerçek API'lere çıkıyordu (madde 20). `.env` ignore'lu ama bir gün biri
`config.py` içine token yapıştırırsa kimse fark etmez. Bu betik CI'da izlenen
dosyaları tarar.

Kullanım:
    python scripts/secret_scan.py            # 0 = temiz, 1 = bulgu var
"""
from __future__ import annotations

import hashlib
import json
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
    # JSON alan adıyla gelen sır: `{"encryptionKey":"<32 karakter>"}`.
    # Neden ayrı desen: `assigned_secret` Python atamasına (`KEY = "..."`) bakıyor
    # ve JSON'u kaçırıyor. Ölçüm (2026-11-02): n8n yedeğindeki `./config`
    # dosyası 56 bayttı, credential deposunu çözen `encryptionKey` içeriyordu
    # ve MEVCUT desenlerle 0 bulgu üretiyordu. Alan adı listesi bilinçli dar:
    # genel bir "herhangi anahtar" deseni depoyu yanlış alarmla doldurur.
    (
        "json_secret_field",
        re.compile(
            r'(?i)"?(?:encryptionKey|encryption_key|apiKey|api_key|secretKey|'
            r'secret_key|accessToken|access_token|refreshToken|refresh_token|'
            r'clientSecret|client_secret|privateKey|private_key)"?\s*[:=]\s*"'
            r'([A-Za-z0-9+/=_\-]{16,})"'
        ),
    ),
]

# Bu değerler gerçek sır değil; desen eşleşse de yok sayılır.
ALLOWLIST_SUBSTRINGS = (
    "example", "placeholder", "your_", "xxx", "dummy", "fake", "test",
    "changeme", "redacted", "[", "]", "<", ">", "${",
)

# "Bu değer yazılmamalı" diyen NİYET işaretleri. Ölçüm (2026-11-02): `json_secret_field`
# deseni eklendikten sonra iki test dosyası kırmızıya döndü — ikisi de gerçek sır
# değil, testin "sızmamalı" demek için kullandığı yer tutucuydu:
#   test_documentary_v2_stage_a.py  → "SHOULD_NOT_APPEAR_IN_SCHEMA"
#   test_publish_status.py          → "should-not-be-written"
# Bu ikisini baseline'a yazmak yanlış olurdu: baseline "geçmişte kabul edilmiş
# gerçek bulgu" demek. Kural dar tutuldu; gerçek bir anahtar bu adlarla gelmez.
SENTINEL_SUBSTRINGS = (
    "should_not", "should-not", "shouldnot", "must_not", "must-not",
    "do_not", "do-not", "not_be_written", "not-be-written", "redacted",
)

# Üretilmiş/ikili içerik ve test fixture'ları taranmaz.
SKIP_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".mp4", ".mp3", ".wav", ".webp", ".gif",
    ".db", ".lock", ".ico", ".zip", ".patch", ".pdf",
)
# NOT: "video-output" burada YOK. Bu liste `git ls-files` sonucuna uygulanıyor;
# izlenen bir dosya zaten commit edilmiş demektir, dolayısıyla onu taramadan
# atlamak sadece körlük üretir. Eklenmesi şu hataya yol açmıştı: `video-output/`
# altında 88 izlenen dosya vardı ve tarayıcı onları hiç görmedi.
SKIP_DIR_PARTS = ("node_modules", ".git", "__pycache__", "_tmp")

# Arşivler: içeriği metin olarak okunamaz, ama SESSİZCE atlanamaz.
# Ölçüm (2026-11-02): geçmişte `backups/otomasyon-yedek-2026-09-05.tar.gz`
# vardı — tam yedek. `iter_history_texts` ikili blob'ları (gzip `\x00` içerir)
# sessizce atladığı için tarayıcı onu hiç görmedi ve "geçmişte yeni sır yok"
# dedi. `.zip` de `SKIP_SUFFIXES`'te olduğundan HEAD taramasında da görünmezdi.
# Sınıfın kuralı: ikili olması "temiz" demek değil, "okunamadı" demek.
ARCHIVE_SUFFIXES = (
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz",
    ".txz", ".7z", ".rar", ".gz", ".bz2", ".xz",
)
# Zip bomb'a karşı: üye sayısı ve toplam açılmış boyut sınırlı.
MAX_ARCHIVE_MEMBERS = 200
MAX_ARCHIVE_BYTES = 20_000_000
# İç içe arşiv derinliği. Neden 3: ölçülen gerçek durum tar.gz → tar → dosya,
# yani 2 katman; bir katman pay bırakıldı. Sınırsız bırakmak zip bomb'a açık
# kapı olurdu (her katman 200 üye açabildiği için üstel büyür).
MAX_ARCHIVE_DEPTH = 3

# ---------------------------------------------------------------------------
# YOL TABANLI DEDEKTÖRLER
#
# Neden ayrı dedektör: bir tarayıcı oturum dosyasının tehlikesi içindeki
# `token="..."` metni değil, DOSYANIN KENDİSİDİR. Chromium `Cookies` dosyası
# SQLite'tır — içeriği ikili, regex'e görünmez. Ölçüm (2026-10-31): geçmişte
# `video-output/tiktok_session/` altında 1015 dosya vardı (`Login Data`,
# `Network/Cookies`, `Local State` dahil) ve içerik tarayıcısı bunları "temiz"
# raporladı. Yol deseni olmadan bu sınıf sızıntı hiç yakalanmaz.
# ---------------------------------------------------------------------------
DANGEROUS_PATH_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("browser_cookies", re.compile(r"(?i)(^|/)cookies(-journal)?$")),
    ("browser_login_data", re.compile(r"(?i)(^|/)login data(-journal)?$")),
    ("browser_local_state", re.compile(r"(?i)(^|/)local state$")),
    ("browser_web_data", re.compile(r"(?i)(^|/)web data(-journal)?$")),
    ("browser_profile_dir", re.compile(r"(?i)(^|/)(tiktok_session|browser_session|user_data)(/|$)")),
    ("ssh_private_key", re.compile(r"(?i)(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)$")),
    ("key_material", re.compile(r"(?i)\.(pem|pfx|p12|key|keystore|jks)$")),
    ("session_state", re.compile(r"(?i)(^|/)(session|storage_state|tokens?)\.json$")),
    # `.env` ile biten her dosya (`prod.env`, `app.env`) — sadece tam `.env`
    # değil. Ölçüm: ilk sürüm `(^|/)\.env$` idi ve geçici depoda `prod.env`
    # sızıntısını KAÇIRDI (uçtan uca test yakaladı).
    ("dotenv", re.compile(r"(?i)\.env$")),
    # Arşiv: içeriği açılamasa bile commit edilmiş bir yedek/zip yolun kendisi
    # bulgudur. `path_is_archive` ile aynı listeyi kullanır.
    (
        "archive_file",
        re.compile(
            r"(?i)\.(zip|tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz|7z|rar|gz|bz2|xz)$"
        ),
    ),
]


def path_is_archive(path: str) -> bool:
    """Yol bir arşiv mi? `ARCHIVE_SUFFIXES` tek doğruluk kaynağı."""
    return path.lower().endswith(ARCHIVE_SUFFIXES)

# Şablon dosyaları gerçek sır taşımaz; yol deseni eşleşse de yok sayılır.
PATH_ALLOWLIST_SUBSTRINGS = ("example", "sample", "template", ".dist", "placeholder")


def scan_path(path: str) -> list[tuple[str, str]]:
    """Yol desenlerine göre (dedektör, eşleşen parça) çiftleri.

    Eşleşen parçayı döndürmek önemli: `browser_profile_dir` bir dizindeki her
    dosyayla eşleşir. Ölçüm: 1015 dosyalık bir Chromium profili 940 ayrı satır
    üretiyordu — operatör için okunamaz. Dizin bir kez raporlanır, tek tek
    hassas dosyalar (`Cookies`, `Login Data`, `Local State`) ayrıca görünür.
    """
    lowered = path.lower()
    if any(tok in lowered for tok in PATH_ALLOWLIST_SUBSTRINGS):
        return []
    out: list[tuple[str, str]] = []
    for name, pattern in DANGEROUS_PATH_PATTERNS:
        m = pattern.search(path)
        if m:
            # Dizin desenlerinde grup 2 asıl dizin adıdır; dosya desenlerinde
            # eşleşmenin tamamı yeterli.
            matched = (m.group(2) if m.re.groups >= 2 and m.group(2) else m.group(0))
            out.append((name, matched))
    return out


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], capture_output=True, check=True
    ).stdout


def history_objects() -> list[tuple[str, str]]:
    """Tüm ref'lerden erişilebilen (blob_sha, path) çiftleri."""
    out = _git("rev-list", "--all", "--objects").decode("utf-8", "replace")
    pairs = []
    for line in out.splitlines():
        if " " not in line:
            continue  # ağaç/commit nesnesi, yol yok
        sha, path = line.split(" ", 1)
        pairs.append((sha, path))
    return pairs


def iter_history_texts(
    pairs: list[tuple[str, str]],
    *,
    max_bytes: int = 2_000_000,
    include_archives: bool = False,
) -> list[tuple[str, str]]:
    """(path, text) — ikili ve aşırı büyük blob'lar atlanır.

    Tek `cat-file --batch` süreci kullanılıyor: blob başına ayrı `git` çağrısı
    1774 blob'da dakikalarca sürüyordu, batch ile 2.3 sn (ölçüldü).

    `include_archives=True`: arşiv blob'ları ikili olduğu için normalde
    atlanırdı. Bu modda açılır ve metin olarak döndürülür. Ölçüm (2026-11-02):
    varsayılan davranış `backups/otomasyon-yedek-2026-09-05.tar.gz`'yi hiç
    görmedi ve tarayıcı "geçmişte yeni sır yok" dedi.
    """
    seen: set[str] = set()
    texts: list[tuple[str, str]] = []
    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    try:
        for sha, path in pairs:
            if sha in seen:
                continue
            seen.add(sha)
            proc.stdin.write((sha + "\n").encode())
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) < 3:
                continue
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # satır sonu
            if include_archives and path_is_archive(path):
                # Arşiv boyutu `max_bytes`'i aşsa bile açılmış içerik sınırlı
                # olduğu için denemeye değer; sınır `read_archive_texts`'te.
                texts.extend(read_archive_texts(path, data))
                continue
            if size > max_bytes or b"\x00" in data[:8000]:
                continue
            texts.append((path, data.decode("utf-8", "replace")))
    finally:
        proc.stdin.close()
        proc.wait()
    return texts


def _archive_members(path: str, data: bytes) -> list[tuple[str, bytes]]:
    """Arşivi açıp (üye yolu, ham baytlar) çiftlerini döndürür.

    `(path, data)` döndürmek önemli: iç içe arşivlerde yalnızca üye adı
    bilinseydi çağıran taraf "bu bir arşiv mi" sorusunu cevaplayamazdı.
    Bozuk/açılamayan arşivde boş liste — istisna fırlatmaz.
    """
    import io
    import tarfile
    import zipfile

    members: list[tuple[str, bytes]] = []
    try:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist()[:MAX_ARCHIVE_MEMBERS]:
                    if info.file_size > MAX_ARCHIVE_BYTES:
                        continue
                    with zf.open(info) as fh:
                        members.append((info.filename, fh.read(MAX_ARCHIVE_BYTES)))
        elif tarfile.is_tarfile(io.BytesIO(data)):
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for member in tf.getmembers()[:MAX_ARCHIVE_MEMBERS]:
                    if not member.isfile() or member.size > MAX_ARCHIVE_BYTES:
                        continue
                    fh = tf.extractfile(member)
                    if fh is not None:
                        members.append((member.name, fh.read(MAX_ARCHIVE_BYTES)))
        elif data[:2] == b"\x1f\x8b":
            # Tek gzip: üye yolu bilinmiyor, arşivin yolunu kullan.
            import gzip

            raw = gzip.decompress(data)[:MAX_ARCHIVE_BYTES]
            members.append((path, raw))
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError, EOFError):
        return []
    return members


def read_archive_texts(path: str, data: bytes) -> list[tuple[str, str]]:
    """Arşiv blob'unu açıp metin üyelerini döndürür: (üye yolu, metin).

    Yalnızca metin gibi görünen üyeler taranır; ikili üyeler (video, sqlite)
    atlanır — onların tehlikesi içeriklerinde değil, varlıklarında. Bu yüzden
    çağıran taraf arşivin kendisini de yol deseniyle ayrıca raporlar.

    ÖNEMLİ — iç içe arşivler açılır (`MAX_ARCHIVE_DEPTH`). Ölçüm (2026-11-02):
    `backups/otomasyon-yedek-2026-09-05.tar.gz` içinde `n8n-data.tar` vardı ve
    bu fonksiyon onu ikili diye atlıyordu. Sonuç: içerideki `./config` —
    56 bayt, n8n credential deposunu çözen `encryptionKey` — hiç okunmadı ve
    tarayıcı "temiz" dedi. İkili olması "temiz" değil, "okunmadı" demek.

    Derinlik sınırı yüzünden açılamayan iç arşivler burada dönmez; onlar
    `unopened_archives()` ile ayrıca alınır ve bulgu sayılır. Böylece
    "derine inmedim" asla "temiz" olmaz.

    Bozuk/açılamayan arşiv **sessizce geçilmez**: boş liste döner ama `path_is_archive`
    sayesinde yol deseni yine bulgu üretir. Böylece "açamadım" asla "temiz" olmaz.
    """
    return _walk_archive(path, data, depth=1)


# Derinlik sınırı yüzünden AÇILAMAYAN iç arşivler: (üye yolu, katman).
# Neden modül düzeyi: `read_archive_texts` imzası testlerde ve CI'da kullanılıyor;
# ikinci bir dönüş değeri eklemek çağıranları kırardı. Tarama başında
# `reset_unopened_archives()` çağrılır, yoksa önceki taramanın kalıntısı raporlanır.
_unopened_archives: list[tuple[str, int]] = []


def unopened_archives() -> list[tuple[str, int]]:
    """Son taramada açılamayan iç arşivler — her biri bir bulgudur."""
    return list(_unopened_archives)


def reset_unopened_archives() -> None:
    _unopened_archives.clear()


def _walk_archive(path: str, data: bytes, *, depth: int, base: str = "") -> list[tuple[str, str]]:
    """Özyinelemeli arşiv yürüyüşü: metin üyeleri döner.

    Derinlik sınırına takılan iç arşivler `_unopened_archives`'e yazılır.
    """
    texts: list[tuple[str, str]] = []
    for name, raw in _archive_members(path, data):
        member_path = f"{base}!{name}" if base else f"{path}!{name}"
        if path_is_archive(name):
            if depth >= MAX_ARCHIVE_DEPTH:
                # Sınıra geldik: sessizce atlamak yerine işaretle.
                _unopened_archives.append((member_path, depth))
                continue
            texts.extend(_walk_archive(path, raw, depth=depth + 1, base=member_path))
            continue
        if b"\x00" in raw[:8000]:
            continue
        texts.append((member_path, raw.decode("utf-8", "replace")))
    return texts




def _sequential_run(value: str, run: int = 10) -> bool:
    """Değer sıralı alfabe/rakam içeriyor mu ("abcdefghij", "0123456789")?

    Test fixture'ları sahtedir ama desen eşleşir. Ölçüm: `31ec209` öncesi
    `test_secret_scan.py` içinde sıralı alfabeden oluşan bir OpenAI anahtarı
    vardı (`sk-` + `a..x`); tarayıcı bunu gerçek bulgu sanıp 7 satır gürültü
    üretti. Hepsini susturmak yerine işaretliyoruz — sahte olup olmadığına
    operatör karar versin.

    NOT: bu docstring'e örneği literal yazmayın; tarayıcı kendi kaynağını
    tarar ve `test_repo_itself_is_clean` kırmızıya döner (bir kez yaşandı).
    """
    lowered = value.lower()
    streak = 1
    for a, b in zip(lowered, lowered[1:]):
        streak = streak + 1 if ord(b) == ord(a) + 1 else 1
        if streak >= run:
            return True
    return False


def _head_texts(paths: set[str]) -> dict[str, str]:
    """HEAD'deki güncel metinler (yalnızca bulgu görülen dosyalar için)."""
    out: dict[str, str] = {}
    for path in paths:
        try:
            out[path] = _git("show", f"HEAD:{path}").decode("utf-8", "replace")
        except subprocess.CalledProcessError:
            continue  # HEAD'de yok
    return out


def finding_key(kind: str, detector: str, path: str, value: str = "") -> str:
    """Baseline karşılaştırması için kararlı anahtar.

    `value` verilirse (içerik bulguları) değerin kısa SHA-256 özeti anahtara
    girer. Neden: anahtar yalnızca (desen, dosya) olsaydı aynı dosyadaki
    FARKLI bir sır aynı anahtara düşer ve baseline onu sessizce yutardı.
    Ölçüldü: ilk sürümde `content:openai_key:...test_secret_scan.py` üç kez
    tekrarlıyordu, yani üç ayrı değer tek anahtardı. Özet geri döndürülemez;
    baseline dosyası sırrı sızdırmaz.
    """
    path = path.replace(chr(92), "/")
    if kind == "content" and value:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"{kind}:{detector}:{path}:{digest}"
    return f"{kind}:{detector}:{path}"


BASELINE_PATH = Path(__file__).with_name("secret_scan_baseline.json")


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["key"] for entry in data.get("accepted", [])}


def scan_history_struct() -> tuple[list[dict], dict[str, int]]:
    """Yapısal bulgular: {"kind", "detector", "path", "detail"}."""
    in_tree = {p.as_posix() for p in tracked_files()}
    counts = {"path_hits": 0, "content_hits": 0, "in_tree": 0}
    findings: list[dict] = []

    pairs = history_objects()

    dir_hits: dict[str, str] = {}
    file_hits: dict[str, str] = {}
    for _, path in pairs:
        for detector, matched in scan_path(path):
            if detector == "browser_profile_dir":
                idx = path.lower().find(matched.lower())
                dir_hits.setdefault(path[: idx + len(matched)], detector)
            else:
                file_hits.setdefault(path, detector)

    for directory, detector in sorted(dir_hits.items()):
        children = sum(1 for _, p in pairs if p.startswith(directory + "/"))
        findings.append({
            "kind": "path",
            "detector": detector,
            "path": directory,
            "detail": directory + f"/ — {children} dosya (geçmişte)",
        })
        counts["path_hits"] += 1

    for path, detector in sorted(file_hits.items()):
        flag = "HEAD'de" if path in in_tree else "sadece geçmişte"
        findings.append({
            "kind": "path",
            "detector": detector,
            "path": path,
            "detail": f"{path} ({flag})",
        })
        counts["path_hits"] += 1

    # HEAD karşılaştırması *değerin* hâlâ orada olmasına bakar, dosyanın
    # var olmasına değil: `31ec209` fixture'ları temizledi ama dosya duruyor.
    # `include_archives=True`: commit edilmiş yedek/zip içeriği de taranır.
    # Varsayılan `False` olsaydı `backups/*.tar.gz` sınıfı yine görünmezdi.
    content_hits: list[tuple[str, int, str, str, str]] = []
    reset_unopened_archives()
    # Arşiv üyelerinin yolu `dis.tar!ic/dosya` biçiminde gelir. Yol desenleri
    # bunlara da uygulanır: bir `Cookies`/`Login Data` dosyası zip İÇİNDE olsa
    # da tehlikelidir ve içeriği ikili olduğu için metin taraması göremez.
    inner_path_hits: dict[str, str] = {}
    for path, text in iter_history_texts(pairs, include_archives=True):
        if "!" in path:
            for detector, _matched in scan_path(path.split("!", 1)[1]):
                if detector != "archive_file":
                    inner_path_hits.setdefault(path, detector)
        for name, lineno, value, snippet in scan_text_values(text):
            content_hits.append((path, lineno, name, value, snippet))

    for path, detector in sorted(inner_path_hits.items()):
        findings.append({
            "kind": "path",
            "detector": detector,
            "path": path,
            "detail": f"{path} (arşiv içinde)",
        })
        counts["path_hits"] += 1

    # Derinlik sınırı yüzünden açılamayan iç arşivler: her biri bulgu.
    # Neden bulgu: "derine inmedim" bilgisi operatöre ulaşmazsa tarayıcı
    # sessizce kör kalır — düzeltmeye çalıştığımız hatanın aynısı.
    for archive_path, depth in sorted(set(unopened_archives())):
        findings.append({
            "kind": "path",
            "detector": "nested_archive_unopened",
            "path": archive_path,
            "detail": (
                f"{archive_path} (iç içe arşiv, katman {depth} — "
                f"MAX_ARCHIVE_DEPTH={MAX_ARCHIVE_DEPTH} sınırı; elle açın)"
            ),
        })
        counts["path_hits"] += 1

    current = _head_texts({p for p, _, _, _, _ in content_hits})
    for path, lineno, name, value, snippet in sorted(set(content_hits)):
        flags = []
        if value in current.get(path, ""):
            flags.append("HEAD'de")
            counts["in_tree"] += 1
        elif path in current:
            flags.append("düzeltilmiş")
        else:
            flags.append("sadece geçmişte")
        if _sequential_run(value):
            flags.append("muhtemelen sahte")
        findings.append({
            "kind": "content",
            "detector": name,
            "path": path,
            "value": value,
            "detail": f"{path}:{lineno}: {name} ({snippet}) ({', '.join(flags)})",
        })
        counts["content_hits"] += 1

    return findings, counts


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def scan_targets(root: Path | None = None) -> list[Path]:
    """İzlenen + izlenmeyen ama ignore'lu olmayan dosyalar (`root`'a göre).

    Neden `git ls-files` yetmiyor: yeni yazılmış (henüz commit edilmemiş) bir
    dosya taranmıyordu. Ölçüldü — `test_secret_scan_history.py` içine sır
    desenine uyan bir literal koydum, yerel tarama "Temiz" dedi, commit edip
    CI'a gidince hem `test` hem `history-scan` kırıldı. Commit öncesi çalışan
    bir kapı, commit'ten sonra ortaya çıkan bir hatayı yakalamıyorsa gereksizdir.

    `root` zorunlu: `git` süreç cwd'sinde çalışır ama `main` dosyaları `root`
    altından okur. İkisi ayrışırsa tarayıcı yanlış ağaca bakar — testte
    `pytest` cwd'si `video-worker` olduğu için tam bu oldu.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
        cwd=str(root) if root is not None else None,
    ).stdout
    seen: list[Path] = []
    for p in out.split("\0"):
        if p:
            candidate = Path(p)
            if candidate not in seen:
                seen.append(candidate)
    return seen


def scan_text_values(text: str) -> list[tuple[str, int, str, str]]:
    """(desen adı, satır, TAM değer, maskeli önek) dörtlüleri.

    Tam değer yalnızca süreç içinde kullanılır (HEAD karşılaştırması için);
    operatöre her zaman maskeli önek gösterilir.
    """
    hits: list[tuple[str, int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            value = m.group(0)
            lowered = value.lower()
            if any(tok in lowered for tok in ALLOWLIST_SUBSTRINGS):
                continue
            if any(tok in lowered for tok in SENTINEL_SUBSTRINGS):
                continue
            # Satır başına tek bulgu: desenler en özelden en gene sıralı, yani
            # `sk-...` hem `openai_key` hem `assigned_secret` ile eşleşse de
            # operatöre tek satır rapor edilir.
            hits.append((name, lineno, value, value[:6] + "…"))
            break
    return hits


def scan_text(text: str) -> list[tuple[str, int, str]]:
    return [(n, ln, snip) for n, ln, _value, snip in scan_text_values(text)]


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    history = "--history" in args
    update = "--update-baseline" in args
    args = [a for a in args if a not in ("--history", "--update-baseline")]
    root = Path(args[0]) if args else Path.cwd()

    if history and update:
        findings, counts = scan_history_struct()
        # Aynı değer iki satırda geçebilir (aynı özet) — baseline'da tek kayıt.
        entries: dict[str, dict] = {}
        for f in findings:
            key = finding_key(f["kind"], f["detector"], f["path"], f.get("value", ""))
            entries.setdefault(key, {
                "key": key,
                "detector": f["detector"],
                "path": f["path"],
                "detail": f["detail"],
            })
        entries_list = list(entries.values())
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "why": (
                        "Geçmişte zaten var olan sır/oturum bulguları. Geçmişi "
                        "yeniden yazmadan silinemez; rotasyon yapılmadan da "
                        "kaybolmaz. Amaç: YENİ sızıntıyı yakalamak."
                    ),
                    "how_to_clear": "git filter-repo ile geçmişi temizleyip bu dosyayı boşaltın",
                    "accepted": entries_list,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Baseline güncellendi: {len(entries_list)} bulgu kabul edildi -> {BASELINE_PATH}")
        return 0

    if history:
        findings, counts = scan_history_struct()
        baseline = load_baseline()
        unknown = [
            f for f in findings
            if finding_key(f["kind"], f["detector"], f["path"], f.get("value", ""))
            not in baseline
        ]
        accepted = len(findings) - len(unknown)

        print(
            f"Geçmiş taraması: {len(findings)} bulgu "
            f"({counts['path_hits']} yol, {counts['content_hits']} içerik); "
            f"{accepted} baseline'da kabul edilmiş, {len(unknown)} YENİ."
        )
        if counts["in_tree"]:
            print(f"  UYARI: {counts['in_tree']} sır HEAD'de hâlâ duruyor.")

        if not unknown:
            print("Geçmişte yeni sır/oturum deseni yok.")
            if findings:
                print("(Bilinen bulgular scripts/secret_scan_baseline.json içinde.")
                print(" Geçmişi `git filter-repo` ile temizledikten sonra baseline'ı")
                print(" boşaltın; liste kendini yeniler.)")
            return 0

        print()
        for f in unknown[:100]:
            print(f"  {f['detail']}")
        if len(unknown) > 100:
            print(f"  … {len(unknown) - 100} bulgu daha")
        print()
        print("YENİ bulgu var: ya sırrı iptal edip geçmişten temizleyin, ya da")
        print("bilinçli kabul ediyorsanız `python scripts/secret_scan.py --history")
        print("--update-baseline` ile kaydedin.")
        return 1

    findings: list[str] = []
    targets = scan_targets(root)
    for path in targets:
        rel = path.as_posix()
        if path.suffix.lower() in SKIP_SUFFIXES and not path_is_archive(rel):
            continue
        if any(part in path.parts for part in SKIP_DIR_PARTS):
            continue
        full = root / path
        if not full.is_file():
            continue
        # Arşiv: metin olarak okunamaz, bu yüzden açılıp içi taranır. Ölçüm
        # (2026-11-02): `.zip` `SKIP_SUFFIXES`'te olduğu için commit edilmiş bir
        # yedek arşivi HEAD taramasında hiç görünmüyordu.
        if path_is_archive(rel):
            try:
                raw = full.read_bytes()
            except OSError:
                continue
            for member_path, text in read_archive_texts(rel, raw):
                for name, lineno, snippet in scan_text(text):
                    findings.append(f"{member_path}:{lineno}: {name} ({snippet})")
            for detector, matched in scan_path(rel):
                findings.append(f"{rel}: {detector} ({matched})")
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, lineno, snippet in scan_text(text):
            findings.append(f"{rel}:{lineno}: {name} ({snippet})")
        # Yol desenleri yalnızca metin okunabildiğinde değil, dosya adında da aranır.
        for detector, matched in scan_path(rel):
            findings.append(f"{rel}: {detector} ({matched})")

    if findings:
        print("Olası sır bulundu:")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"Temiz: {len(targets)} dosyada sır deseni bulunamadı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
