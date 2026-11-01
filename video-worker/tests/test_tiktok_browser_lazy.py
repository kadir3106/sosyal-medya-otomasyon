"""`app/publishers/tiktok_browser.py` — tembel import ve taşınabilir oturum yolu.

Madde 28: bu modülün TEPESİNDE `from playwright.sync_api import ...` vardı.
playwright `requirements.txt`'te olmadığı için modül hiç import edilemiyordu;
çağıran taraf bunu ancak `ImportError` ile anlıyordu ve tek `except Exception`
yüzünden operatör hiçbir şey görmüyordu.

Artık:
- modül her ortamda import edilebilir (playwright tembel),
- `has_active_tiktok_session()` playwright'e ihtiyaç duymaz,
- `upload_via_tiktok_browser()` playwright yoksa `PLAYWRIGHT_MISSING` ile döner,
- oturum dizini `TIKTOK_SESSION_DIR` ile taşınabilir (konteynerde volume).
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def fresh_tiktok_browser(monkeypatch):
    """Modülü her testte sıfırdan import et (SESSION_DIR import anında okunuyor)."""

    def _load():
        for name in list(sys.modules):
            if name == "app.publishers.tiktok_browser":
                del sys.modules[name]
        module = importlib.import_module("app.publishers.tiktok_browser")
        return importlib.reload(module)

    return _load


def test_module_imports_without_playwright(fresh_tiktok_browser, monkeypatch):
    """playwright KURULU DEĞİLKEN modül import edilebilmeli.

    `sys.modules["playwright"] = None` Python'da "import'u burada durdur"
    demektir: her import denemesi `ModuleNotFoundError` verir. Modül tepesinde
    eager import olsaydı bu test `ImportError` ile düşerdi.
    """
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    module = fresh_tiktok_browser()

    assert module.PLAYWRIGHT_MISSING
    assert "playwright" in module.PLAYWRIGHT_MISSING.lower()


def test_has_active_session_works_without_playwright(fresh_tiktok_browser, monkeypatch, tmp_path):
    """Oturum kontrolü playwright gerektirmemeli."""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    monkeypatch.setenv("TIKTOK_SESSION_DIR", str(tmp_path))
    module = fresh_tiktok_browser()

    assert module.has_active_tiktok_session() is False

    (tmp_path / "Default").mkdir()
    (tmp_path / "Default" / "Cookies").write_bytes(b"x")
    assert module.has_active_tiktok_session() is True


def test_upload_returns_clear_error_when_playwright_missing(
    fresh_tiktok_browser, monkeypatch, tmp_path
):
    """playwright yoksa: istisna fırlatmak yerine AÇIK mesajla dönmeli.

    İstisna fırlatsaydı çağırandaki `except Exception` onu yine yutardı;
    dönüş değeri çağıranın `error == PLAYWRIGHT_MISSING` ile ayırt etmesini
    mümkün kılıyor.
    """
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "Cookies").write_bytes(b"x")
    monkeypatch.setenv("TIKTOK_SESSION_DIR", str(session_dir))
    module = fresh_tiktok_browser()

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    result = module.upload_via_tiktok_browser(str(video), "Başlık")

    assert result["status"] == "error"
    assert result["error"] == module.PLAYWRIGHT_MISSING


def test_session_dir_honours_env(fresh_tiktok_browser, monkeypatch, tmp_path):
    """`TIKTOK_SESSION_DIR` verilirse o kullanılmalı (konteynerde volume yolu)."""
    monkeypatch.setenv("TIKTOK_SESSION_DIR", str(tmp_path / "custom-session"))
    module = fresh_tiktok_browser()
    assert module.SESSION_DIR == Path(str(tmp_path / "custom-session"))


def test_session_dir_defaults_to_repo_video_output(fresh_tiktok_browser, monkeypatch):
    """Env yoksa eski varsayılan korunmalı (yerel kullanım bozulmasın)."""
    monkeypatch.delenv("TIKTOK_SESSION_DIR", raising=False)
    module = fresh_tiktok_browser()
    assert module.SESSION_DIR.name == "tiktok_session"
    assert module.SESSION_DIR.parent.name == "video-output"


def test_missing_session_short_circuits_before_playwright(fresh_tiktok_browser, monkeypatch, tmp_path):
    """Oturum yoksa playwright hiç denenmemeli: ucuz ve doğru sıra."""
    monkeypatch.setenv("TIKTOK_SESSION_DIR", str(tmp_path / "empty"))

    called = {"playwright": 0}
    fake_pw = types.ModuleType("playwright")

    class _Sync:
        def __call__(self):
            called["playwright"] += 1
            raise AssertionError("oturum yokken playwright çağrılmamalı")

    fake_api = types.ModuleType("playwright.sync_api")
    fake_api.sync_playwright = _Sync()  # type: ignore[attr-defined]
    fake_pw.sync_api = fake_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", fake_pw)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_api)
    module = fresh_tiktok_browser()

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    result = module.upload_via_tiktok_browser(str(video), "Başlık")

    assert result["status"] == "error"
    assert "oturum" in result["error"].lower()
    assert called["playwright"] == 0
