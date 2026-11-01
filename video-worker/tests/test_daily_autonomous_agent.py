"""`scripts/daily_autonomous_agent.py` — otonom yayın turunun gerçek davranışı.

Bu betik daha önce hiç test edilmiyordu; `--director` çökmesi (madde 27) tam bu
yüzden fark edilmeden yaşadı. `tests/test_natural_message_crashes.py` yalnızca
imza↔çağrı tutarlılığını kilitliyordu. Burada davranışın kendisi sınanıyor.

Testlerin odağı **yanlış yayın yapmamak**. Bu betik YouTube'a `public` yükler;
geri alınamaz. Buradaki her senaryo şu soruya cevap veriyor: "Hata/iptal/belirsizlik
durumunda platformlara bir şey gidiyor mu?"

Ağ erişimi gerekmiyor: `tests/conftest.py` dış ağı kapatıyor, pipeline modunu
sabitliyor, retry'ları sıfırlıyor. Ek olarak burada `.env`'den gelebilecek tüm
platform kimlik bilgileri boşaltılıyor — yoksa 14/23 credential gerçekten canlı.
"""
from __future__ import annotations

import asyncio
import datetime
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import daily_autonomous_agent as agent  # noqa: E402
from app.config import config  # noqa: E402

TOPIC = "The Silent Architecture of Power"

#: `execute_daily_run`'ın `generate_video`'dan beklediği alanlar.
FAKE_RESULT = {
    "video_path": "/tmp/video.mp4",
    "split_screen_path": "/tmp/split.mp4",
    "title": "Test Başlık",
    "description": "Test açıklama",
    "tags": ["#test"],
    "pinned_comment": "Yorum kancası",
    "thumbnail_path": "",
}

_OPTIONAL_PLATFORM_ATTRS = (
    "META_PAGE_ACCESS_TOKEN",
    "META_IG_USER_ID",
    "META_PAGE_ID",
    "THREADS_USER_ID",
    "THREADS_ACCESS_TOKEN",
    "X_CLIENT_ID",
    "X_CLIENT_SECRET",
    "X_REFRESH_TOKEN",
    "PINTEREST_CLIENT_ID",
    "PINTEREST_CLIENT_SECRET",
    "PINTEREST_REFRESH_TOKEN",
    "PINTEREST_BOARD_ID",
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Tüm dış etkileri kes: medya dizini geçici, hiçbir platform yapılandırılmamış.

    `config` sınıf nitelikleri üzerinden okunuyor; `patch.multiple` çıkışta geri
    alıyor, yani testler birbirinin kimlik bilgilerini sızdırmıyor.
    """
    monkeypatch.delenv("ALLOW_AUTONOMOUS_PUBLISH", raising=False)
    with patch.multiple(
        config,
        MEDIA_DIR=str(tmp_path),
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_CHAT_ID="",
        TUNNEL_LOG_PATH=str(tmp_path / "tunnel.log"),
        TIKTOK_TOKEN_PATH=str(tmp_path / "tiktok_token.json"),
        **{attr: "" for attr in _OPTIONAL_PLATFORM_ATTRS},
    ), patch.object(agent, "select_next_topic", return_value=TOPIC) as select, patch.object(
        agent, "release_topic"
    ) as release, patch.object(
        agent, "send_message", return_value=True
    ) as send, patch.object(
        agent, "upload_to_youtube", return_value={"status": "success", "video_id": "vid1"}
    ) as yt, patch(
        "app.publishers.tiktok_browser.has_active_tiktok_session", return_value=False
    ):
        yield {
            "release": release,
            "send": send,
            "youtube": yt,
            "select": select,
            "tmp_path": tmp_path,
        }


def _run(**kwargs):
    return asyncio.run(agent.execute_daily_run(**kwargs))


# --------------------------------------------------------------------------- #
# Yayın kapısı — bu betiğin en tehlikeli kısmı
# --------------------------------------------------------------------------- #


def test_publish_gate_blocks_when_env_flag_missing(isolated):
    """Bayrak yoksa video üretilir ama HİÇBİR platforma gitmez."""
    with patch.object(agent, "generate_video", return_value=FAKE_RESULT) as gen:
        result = _run()

    assert gen.called, "video üretilmeliydi"
    assert result is None
    assert not isolated["youtube"].called, "yayın kapısı delinmiş: YouTube'a gidildi"


@pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE ", "True!", "evet"])
def test_publish_gate_blocks_lookalike_values(isolated, monkeypatch, value):
    """`"true"` dışındaki her şey yayını engeller — sessiz yazım hatası yayın yapmasın.

    Kod `os.environ.get(...).lower() != "true"` ile karşılaştırıyor, yani
    `"TRUE "` (sondaki boşluk) veya `"1"` yayını kapatır. Bu davranış kazara
    değişirse gerçek public yayın başlar; burada kilitleniyor.
    """
    monkeypatch.setenv("ALLOW_AUTONOMOUS_PUBLISH", value)
    with patch.object(agent, "generate_video", return_value=FAKE_RESULT):
        result = _run()

    assert result is None
    assert not isolated["youtube"].called


def test_publish_gate_opens_only_for_exact_true(isolated, monkeypatch):
    monkeypatch.setenv("ALLOW_AUTONOMOUS_PUBLISH", "TRUE")  # büyük harf kabul
    with patch.object(agent, "generate_video", return_value=FAKE_RESULT), patch(
        "app.channel_growth.analyze_channel_growth", side_effect=RuntimeError("yok")
    ):
        result = _run()

    assert result == "https://youtube.com/shorts/vid1"
    assert isolated["youtube"].call_count == 1


def test_generation_failure_releases_topic_and_raises(isolated):
    """Üretim çökerse konu havuza geri bırakılır ve hata yukarı propaglanır.

    Konu geri bırakılmazsa o konu 'kullanıldı' sayılır ve havuz sessizce tükenir.
    """
    with patch.object(agent, "generate_video", side_effect=RuntimeError("render patladı")):
        with pytest.raises(RuntimeError, match="render patladı"):
            _run()

    isolated["release"].assert_called_once()
    assert isolated["release"].call_args[0][0] == TOPIC
    assert not isolated["youtube"].called


def test_generation_failure_notifies_operator_when_telegram_configured(isolated):
    with patch.multiple(config, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42"), patch.object(
        agent, "generate_video", side_effect=RuntimeError("kota bitti")
    ):
        with pytest.raises(RuntimeError):
            _run()

    sent = isolated["send"].call_args[0][2]
    assert TOPIC in sent
    assert "kota bitti" in sent


# --------------------------------------------------------------------------- #
# Trend → havuz geri düşüşü
# --------------------------------------------------------------------------- #


def test_trend_failure_falls_back_to_pool(isolated):
    """Trend kaynağı çökerse tur iptal edilmez, havuzdan devam edilir."""
    with patch(
        "app.trends.get_trending_viral_topic", side_effect=RuntimeError("Google 429")
    ), patch.object(agent, "generate_video", return_value=FAKE_RESULT) as gen:
        _run(use_trend=True)

    # Havuz konusu ile üretim yapıldı — trend hatası turu öldürmedi.
    assert gen.call_args.kwargs["topic"] == TOPIC


def test_trend_success_skips_pool(isolated):
    with patch(
        "app.trends.get_trending_viral_topic", return_value="Canlı Trend Konusu"
    ), patch.object(agent, "generate_video", return_value=FAKE_RESULT) as gen:
        _run(use_trend=True)

    assert gen.call_args.kwargs["topic"] == "Canlı Trend Konusu"
    isolated["select"].assert_not_called()


# --------------------------------------------------------------------------- #
# Yönetmen modu — onay / iptal / zaman aşımı
# --------------------------------------------------------------------------- #


class _Clock:
    """`time.time()` yerine geçer: 0, sonra 100, 200… böylece döngü 1 tur döner."""

    def __init__(self, step: int = 100):
        self.calls = 0
        self.step = step

    def __call__(self) -> float:
        self.calls += 1
        return 0.0 if self.calls == 1 else float(self.step * (self.calls - 1))


class _FakeAsyncio:
    async def sleep(self, _seconds):
        return None


def _updates(*updates):
    return {"result": list(updates)}


#: `execute_daily_run` `job_id`'yi `datetime.now()`'dan üretiyor:
#: `auto_%Y%m%d_%H%M%S`. Onay/iptal callback verisi bu kimliğe bağlı olduğu
#: için saat sabitlenmeden test edilemez — aksi halde `cancel:auto_x` hiçbir
#: gerçek işle eşleşmez ve döngü zaman aşımına düşer (ilk denemede tam bu oldu).
FROZEN_JOB_ID = "auto_20261031_183000"


def _director_setup(monkeypatch):
    """Yönetmen modu için: sabit saat, gerçek uyku yok."""
    monkeypatch.setenv("ALLOW_AUTONOMOUS_PUBLISH", "true")
    monkeypatch.setattr(agent, "datetime", _frozen_datetime(18, 30))
    monkeypatch.setattr(agent.time, "time", _Clock())
    monkeypatch.setattr(agent.asyncio, "sleep", _FakeAsyncio().sleep)


def test_job_id_is_derived_from_frozen_clock(isolated, monkeypatch):
    """Sabit saatin gerçekten `FROZEN_JOB_ID`'yi ürettiğini doğrular.

    Bu kontrol olmadan diğer testler sessizce yanlış senaryoyu koşabilir:
    callback verisi eşleşmez, döngü zaman aşımına düşer ve test 'geçer' ama
    aslında iptal dalını hiç sınamamış olur.
    """
    _director_setup(monkeypatch)
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return FAKE_RESULT

    with patch.object(agent, "generate_video", side_effect=fake_generate):
        _run()

    assert captured["job_id"] == FROZEN_JOB_ID


def test_director_cancel_returns_none_and_never_publishes(isolated, monkeypatch):
    """İptal butonu: tur biter, hiçbir platforma gidilmez, konu havuza DÖNMEZ.

    Konu geri bırakılmıyor çünkü video başarıyla üretildi — sadece yayınlanmadı.
    Geri bırakmak aynı konuyu yarın yeniden üretmek olurdu.
    """
    _director_setup(monkeypatch)
    updates = _updates(
        {"update_id": 1, "callback_query": {"id": "cq", "data": f"cancel:{FROZEN_JOB_ID}"}}
    )
    with patch.multiple(config, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42"), patch(
        "app.telegram_bot.get_updates", return_value=updates
    ), patch("app.telegram_bot.answer_callback_query"), patch.object(
        agent, "generate_video", return_value=FAKE_RESULT
    ):
        result = _run(director_mode=True)

    assert result is None
    assert not isolated["youtube"].called, "iptal edilen video yayınlandı"
    assert not isolated["release"].called


def test_director_timeout_publishes_anyway(isolated, monkeypatch):
    """Zaman aşımı bilinçli davranış: yanıt gelmezse otomatik yayınlanır.

    Bu, Telegram mesajındaki "yanıt gelmezse otomatik yayınlanır" sözüyle
    tutarlı. Değişirse (ör. sessizce engellenirse) operatör bunu bilmeli.
    """
    _director_setup(monkeypatch)
    with patch.multiple(config, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42"), patch(
        "app.telegram_bot.get_updates", return_value={"result": []}
    ), patch(
        "app.channel_growth.analyze_channel_growth", side_effect=RuntimeError("yok")
    ), patch.object(agent, "generate_video", return_value=FAKE_RESULT):
        result = _run(director_mode=True)

    assert result is not None
    assert isolated["youtube"].call_count == 1


def test_director_approval_publishes(isolated, monkeypatch):
    _director_setup(monkeypatch)
    updates = _updates(
        {"update_id": 1, "callback_query": {"id": "cq", "data": f"pub:{FROZEN_JOB_ID}"}}
    )
    with patch.multiple(config, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42"), patch(
        "app.telegram_bot.get_updates", return_value=updates
    ), patch("app.telegram_bot.answer_callback_query"), patch(
        "app.channel_growth.analyze_channel_growth", side_effect=RuntimeError("yok")
    ), patch.object(agent, "generate_video", return_value=FAKE_RESULT):
        result = _run(director_mode=True)

    assert result is not None
    assert isolated["youtube"].call_count == 1


def test_director_without_telegram_falls_through_to_publish(isolated, monkeypatch):
    """Telegram yapılandırılmamışsa yönetmen modu sessizce atlanır, yayın devam eder.

    Bu tehlikeli bir davranış: `--director` "onay al" demek, ama token yoksa
    onay alınamaz ve yine de yayınlanır. Davranış kilitleniyor ki bilinçli
    bir değişiklik gerektirsin.
    """
    monkeypatch.setenv("ALLOW_AUTONOMOUS_PUBLISH", "true")
    with patch(
        "app.channel_growth.analyze_channel_growth", side_effect=RuntimeError("yok")
    ), patch.object(agent, "generate_video", return_value=FAKE_RESULT):
        result = _run(director_mode=True)

    assert result is not None
    assert isolated["youtube"].call_count == 1


# --------------------------------------------------------------------------- #
# Zamanlayıcı — günde tek yayın
# --------------------------------------------------------------------------- #


class _StopLoop(Exception):
    """`time.sleep` yerine: N turdan sonra döngüyü kır (döngü sonsuz)."""


def _frozen_datetime(hour: int, minute: int):
    """`agent.datetime` yerine: `datetime.datetime.now()` sabitlenir."""

    class _Frozen(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 31, hour, minute, 0)

    return type("_Mod", (), {"datetime": _Frozen})


def test_scheduler_runs_at_most_once_per_day(monkeypatch):
    """Döngü 30 sn'de bir uyanıyor; aynı gün ikinci kez yayın YAPILMAMALI.

    `last_run_day` kontrolü olmasaydı her 30 saniyede bir video yayınlanırdı —
    yani günde 2880 kez.
    """
    sleeps = {"n": 0}
    attempts = {"n": 0}

    def fake_sleep(_seconds):
        sleeps["n"] += 1
        if sleeps["n"] >= 3:  # 2 tur tamamlansın
            raise _StopLoop

    def fake_run(_coro):
        _coro.close()  # gerçek asyncio.run bekleyip kapattığı için uyarı çıkmasın
        attempts["n"] += 1

    monkeypatch.setattr(agent, "datetime", _frozen_datetime(18, 30))
    monkeypatch.setattr(agent.time, "sleep", fake_sleep)
    monkeypatch.setattr(agent.asyncio, "run", fake_run)

    with pytest.raises(_StopLoop):
        agent.run_scheduler_loop(target_hour=18, target_minute=30)

    assert attempts["n"] == 1, "aynı gün içinde birden fazla tur çalıştı"


def test_scheduler_retries_after_failure(monkeypatch):
    """Başarısız tur `last_run_day`'i işaretlemez; sonraki uyanışta yeniden denenir."""
    sleeps = {"n": 0}
    attempts = {"n": 0}

    def fake_sleep(_seconds):
        sleeps["n"] += 1
        if sleeps["n"] >= 3:
            raise _StopLoop

    def fake_run(_coro):
        _coro.close()
        attempts["n"] += 1
        raise RuntimeError("üretim çöktü")

    monkeypatch.setattr(agent, "datetime", _frozen_datetime(18, 30))
    monkeypatch.setattr(agent.time, "sleep", fake_sleep)
    monkeypatch.setattr(agent.asyncio, "run", fake_run)

    with pytest.raises(_StopLoop):
        agent.run_scheduler_loop(target_hour=18, target_minute=30)

    # 3 uyanış = 3 başarısız tur: her hatadan sonra yeniden denendi, yani
    # `last_run_day` işaretlenmedi. 1 olsaydı ilk hatadan sonra döngü susmuştu.
    assert attempts["n"] == 3, "hatadan sonra yeniden denenmedi"


def test_scheduler_does_not_run_before_target_time(monkeypatch):
    sleeps = {"n": 0}
    attempts = {"n": 0}

    def fake_sleep(_seconds):
        sleeps["n"] += 1
        if sleeps["n"] >= 2:
            raise _StopLoop

    def fake_run(_coro):
        attempts["n"] += 1

    monkeypatch.setattr(agent, "datetime", _frozen_datetime(9, 0))
    monkeypatch.setattr(agent.time, "sleep", fake_sleep)
    monkeypatch.setattr(agent.asyncio, "run", fake_run)

    with pytest.raises(_StopLoop):
        agent.run_scheduler_loop(target_hour=18, target_minute=30)

    assert attempts["n"] == 0


