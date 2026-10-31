"""Geçmişte sessizce çöken iki yol — regresyon kilidi.

Her ikisi de ruff'ın yüksek sinyalli kapısında (`--select E9,F63,F7,F82`)
bulundu, sonra **çalıştırılarak** kanıtlandı:

1. `scripts/daily_autonomous_agent.py` — `--director` bayrağı
   `execute_daily_run(use_trend=..., director_mode=...)` çağırıyordu ama
   fonksiyonun imzasında `director_mode` yoktu:
   `TypeError: unexpected keyword argument 'director_mode'`. Yani CLI'daki
   yönetmen modu *hiç* çalışmadı.

2. `app/telegram_bot.py` — `intent == "generate_video"` dalı tanımlanmamış
   `pending_path`'i okuyordu: `NameError: name 'pending_path' is not defined`.
   Telegram'dan "yeni video yap" yazan operatör çökme görüyordu.

Bu betik `scripts/` altında olduğu için hiçbir test onu import etmiyordu;
kırılma ancak elle çalıştırılınca görülürdü. Bu testler o boşluğu kapatıyor.
"""
import ast
import asyncio
import inspect
import json
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def test_execute_daily_run_accepts_director_mode():
    """CLI `--director` gerçekten iletilebilmeli (eskiden TypeError)."""
    import daily_autonomous_agent as agent

    params = inspect.signature(agent.execute_daily_run).parameters
    assert "director_mode" in params
    assert params["director_mode"].default is False


def test_director_flag_callsite_matches_signature():
    """Kaynaktaki çağrı ile imza ayrışmasın — asıl hata buydu.

    Çalıştırmadan doğrulanıyor: `execute_daily_run` gerçek bir video üretir ve
    yayınlar, testte çağrılamaz. AST, iki tarafın aynı anahtar kümesini
    kullandığını kanıtlıyor.
    """
    source = (_SCRIPTS / "daily_autonomous_agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    run_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_daily_run"
    ]
    assert len(run_defs) == 1
    accepted = {a.arg for a in run_defs[0].args.args}

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_daily_run"
    ]
    assert calls, "çağrı bulunamadı"
    for call in calls:
        passed = {kw.arg for kw in call.keywords if kw.arg}
        unknown = passed - accepted
        assert not unknown, f"imzada olmayan argüman: {unknown}"


def test_handle_natural_message_generate_uses_pending_store(tmp_path):
    """`generate_video` dalı pending kaydını okumalı, NameError vermemeli."""
    from app.telegram_bot import handle_natural_message

    (tmp_path / "pending.json").write_text(
        json.dumps({"job_id": "pending-1", "title": "Bekleyen Video"}), encoding="utf-8"
    )
    sent: list[str] = []

    def fake_send(token, chat_id, text, reply_markup=None):
        sent.append(text)

    with patch("app.telegram_bot.send_message", side_effect=fake_send):
        # Çökme olursa NameError testi düşürür; üretim başlamaz çünkü
        # bekleyen iş kontrolü üretimden ÖNCE dönüyor.
        asyncio.run(
            handle_natural_message(
                "yeni video yap",
                "TOKEN",
                "123",
                str(tmp_path),
                publish_fn=lambda p: {},
                cleanup_fn=lambda f: None,
            )
        )

    assert sent, "operatöre mesaj gitmedi"
    assert "Bekleyen Video" in sent[0]


def test_handle_natural_message_generate_without_pending_does_not_crash(tmp_path):
    """Bekleyen iş yokken de çökmemeli: üretim arka planda başlar.

    `_run_bg` gerçek render çağırır, bu yüzden `remotion_runner` import'u
    engelleniyor — testin konusu NameError, render değil.
    """
    from app.telegram_bot import handle_natural_message

    with patch("app.telegram_bot.send_message"), patch(
        "app.remotion_runner.run_remotion_pipeline", side_effect=RuntimeError("test")
    ) as mock_render:
        asyncio.run(
            handle_natural_message(
                "yeni video yap",
                "TOKEN",
                "123",
                str(tmp_path),
                publish_fn=lambda p: {},
                cleanup_fn=lambda f: None,
            )
        )
        # Arka plan görevi kuyruğa alındı; NameError olsaydı buraya gelinmezdi.
        assert mock_render.call_count <= 1
