"""Shared test guards — keep the suite hermetic.

Four guards, all opt-out via the `live` marker:

1. **External network is blocked.** Measured on the real suite: 203 outbound
   connection attempts across 100 tests, yet the suite still passes with them
   blocked (exit 0). So they are leaky background calls, not dependencies —
   `_ensure_synthetic_ambient`'s ffmpeg helpers, Pollinations image fallback,
   Wikipedia fact-verification, and unmocked publishers triggered by the real
   `.env` (14 of 23 credentials are live locally). They made runs slow and
   flaky and spent real API quota. Loopback stays open: Starlette's TestClient
   builds its anyio portal over a local socket.

2. **Production HTTP retries are disabled.** `app.http_client.session` retries 3
   times with a 1.5 backoff factor. Guard 1 makes every leaked call fail, but the
   retry policy would still pay the whole backoff first: measured, that turned a
   72 s run into 344 s. Retries exist for flaky real APIs; in tests there is
   nothing to retry.

3. Ambient `.env` leaks DIRECTOR_ENABLED/DOCUMENTARY_ENGINE_V2. The pipeline
   reads those at call time, so a test that mocks the legacy stock path
   silently runs the real Director path instead: live Pexels + LLM calls, 429
   retries (~30 s each), and the mocked functions never get called.

4. pipeline.refine_script hits Wikipedia + the LLM quality editor. Tests that
   assert on real refinement behaviour call app.script_quality.refine_script
   directly and are unaffected.
"""
from __future__ import annotations

import shutil
import socket

import pytest

from app.script_quality import ScriptQualityResult

_PIPELINE_MODE_ENV = ("DIRECTOR_ENABLED", "DOCUMENTARY_ENGINE_V2")

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

# ffmpeg/ffprobe gerektiren testler. Yalnızca kod yolu gerçekten ffmpeg çağırıyorsa
# buraya eklenir; mock'lanmış render testleri etkilenmez.
_REQUIRES_FFMPEG_PREFIXES = (
    "tests/test_documentary_v2_stage_e.py",
    "tests/test_documentary_v2_stage_f.py",
    "tests/test_documentary_v2_stage_f1.py",
    "tests/test_phase_a_quality.py",
    "tests/test_pipeline.py",
    "tests/test_pipeline_pending.py",
)


def requires_ffmpeg(reason: str = "ffmpeg/ffprobe not installed") -> pytest.MarkDecorator:
    """Ağır ortam bağımlılığı için açık skip; ham FileNotFoundError yerine."""

    return pytest.mark.skipif(not HAS_FFMPEG, reason=reason)


def needs_ffmpeg(nodeid: str) -> bool:
    """Bu test düğümü ffmpeg/ffprobe çağırıyor mu?

    Ayrı fonksiyon: fixture'ın kararı alt süreç başlatmadan test edilebilsin.
    (İlk denemede guard'ı `PATH=""` ile alt süreçte sınamıştım; Python PATH'siz
    başlayamadığı için test 41 dakika asıldı. Kararı saf fonksiyona taşıdım.)
    """
    return any(nodeid.startswith(p) for p in _REQUIRES_FFMPEG_PREFIXES)


def _is_external(address) -> bool:
    """True only for real outbound destinations; loopback/AF_UNIX stay usable."""
    if not isinstance(address, tuple) or len(address) < 2:
        return False  # AF_UNIX path etc.
    host = str(address[0])
    return not (host in _LOOPBACK or host.startswith("127."))


class ExternalNetworkBlocked(OSError):
    """Raised instead of dialling out. Deliberately NOT a requests exception.

    requests/urllib3 retry ConnectionError and Timeout (3 attempts, 1.5 backoff
    factor). If this looked like a connection error, every blocked call would
    cost ~19-27 s of backoff: measured on the full suite, the block turned a
    72 s run into 312 s. A plain OSError propagates without retry.
    """


@pytest.fixture(autouse=True)
def _skip_without_ffmpeg(request):
    """ffmpeg gerektiren testleri, eksikse AÇIK bir sebeple atla.

    Ölçüm: CI'ın ilk gerçek koşusunda 15 test `FileNotFoundError: 'ffmpeg'` ile
    düştü. Bu bir kod hatası değil ortam eksiğiydi, ama ham traceback operatöre
    "kod bozuk" gibi görünüyor. Skip hem doğru bilgi verir hem CI'ı yeşil tutar
    (kaynağı olmayan bir bağımlılık yüzünden değil, ölçülmüş bir eksiklik
    yüzünden).

    `HAS_FFMPEG` tek yerde tanımlı olduğu için yeni test dosyası eklerken
    listeye bakmak yeterli.
    """
    if HAS_FFMPEG:
        return
    if needs_ffmpeg(request.node.nodeid):
        pytest.skip("ffmpeg/ffprobe not installed")


@pytest.fixture(autouse=True)
def _disable_http_retries(request):
    """Drop the production retry policy for the duration of each test.

    `app.http_client.session` is a module-level singleton with Retry(total=3,
    backoff_factor=1.5). With the external-network guard below, every leaked call
    paid the full backoff before failing: measured on the full suite, 72 s -> 344 s.
    Retries exist for flaky real APIs; in tests there is nothing to retry.

    The previous adapters are restored afterwards: mounting permanently on a
    module-level session leaked into test_http_client, which asserts the
    production policy (Retry.total == 3).
    """
    if request.node.get_closest_marker("live"):
        return
    if request.node.nodeid.startswith("tests/test_http_client.py"):
        # These two tests assert the production retry policy itself; stubbing it
        # would make them meaningless. Yield without touching the session.
        yield
        return
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    import app.http_client as http_client

    # session.adapters is a plain dict; mounting is a plain assignment. Copy the
    # dict and restore it, instead of re-mounting adapters we never inspected
    # (get_adapter() can synthesise a default for an unmounted prefix).
    saved = dict(http_client.session.adapters)
    no_retry = Retry(total=0)
    for prefix in ("http://", "https://"):
        http_client.session.mount(prefix, HTTPAdapter(max_retries=no_retry))
    try:
        yield
    finally:
        http_client.session.adapters.clear()
        http_client.session.adapters.update(saved)


@pytest.fixture(autouse=True)
def _block_external_network(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return

    real_create = socket.create_connection
    real_connect = socket.socket.connect

    def _deny(address) -> None:
        raise ExternalNetworkBlocked(
            f"external network is blocked in tests ({address}); "
            "mark the test `live` to allow it"
        )

    def create_connection(address, *a, **kw):
        if _is_external(address):
            _deny(address)
        return real_create(address, *a, **kw)

    def connect(self, address, *a, **kw):
        if _is_external(address):
            _deny(address)
        return real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture(autouse=True)
def _default_legacy_pipeline_mode(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return
    for name in _PIPELINE_MODE_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _stub_pipeline_refine_script(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return
    import app.pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "refine_script",
        lambda script, **kw: ScriptQualityResult(
            raw_script=script or "", final_script=script or ""
        ),
    )
