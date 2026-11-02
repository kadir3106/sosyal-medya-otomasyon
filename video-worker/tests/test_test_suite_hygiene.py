"""Test dosyalarının kendi sağlığı — ölçüldü, çünkü sessizce bozulabiliyorlar.

Neden bu dosya var: bu depoda test düzenlemeleri sırasında **üç kez** aynı hata
oluştu — yeni bir test, var olan bir testin gövdesinin ortasına eklendi. Sonuçlar:

  * `test_seal_leak_copies.py`: bir testin gövdesine yetim bir blok yapıştı
    (satır 195-206). Test hâlâ **geçiyordu**, çünkü yetim blok bir docstring'den
    ibaretti. `test_not_a_sealed_file_rejected` ise kaybolmuştu — isimle
    çalıştıran bir komut `ERROR: not found` alırdı.
  * `test_verify_leak_rotation.py`: `test_tiktok_verdict_says_web_cannot_revoke`
    iki kez tanımlandı ve ilk tanım `con.execute` satırında kesiliyordu. İkinci
    tanım birincisini ezip testi yeşil tuttu; assert'leri olmayan ölü kod kaldı.

Ortak özellik: **suite yeşil kaldı**. Bu yüzden "testler geçiyor" bu sınıfı
yakalamıyor. Aşağıdaki testler yapısal: tekrar eden isim ve ölü kod arıyorlar.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _test_files() -> list[Path]:
    return sorted(TESTS_DIR.glob("test_*.py"))


def test_no_duplicate_test_names():
    """Aynı isimli iki test = biri sessizce ölü. pytest ikisini de toplar ama
    hangisinin kazandığı dosya sırasına bağlı; sonraki ilkini ezer."""
    duplicates: list[str] = []
    for path in _test_files():
        names = [
            node.name
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                duplicates.append(f"{path.name}: {name}")
            seen.add(name)
    assert not duplicates, "tekrar eden test isimleri: " + ", ".join(duplicates)


def test_no_test_function_is_empty():
    """Gövdesi yalnız docstring olan test hiçbir şey ölçmez — hep yeşil.

    Bu, "insert bir testin gövdesini böldü" hatasının en sinsi hâli: yetim
    docstring'e dönüşen blok yeni bir test gibi görünür ve geçer.
    """
    hollow: list[str] = []
    for path in _test_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            body = list(node.body)
            # Yalnız docstring varsa (ya da hiç gövde yoksa) hiçbir şey ölçmüyor.
            if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant
            ) and isinstance(body[0].value.value, str):
                body = body[1:]
            if not body:
                hollow.append(f"{path.name}::{node.name} (satır {node.lineno})")
    assert not hollow, "gövdesi boş testler: " + ", ".join(hollow)


def test_no_orphan_statements_after_test_function():
    """Bir testin gövdesinden sonra, girintisi testin İÇİNDE kalan anlamsız blok.

    Ölçülen hata deseni: `test_seal_leak_copies.py`'de bir fonksiyonun gövdesine
    docstring + `with pytest.raises(...)` bloğu yapıştı. Sözdizimi geçerli olduğu
    için hiçbir araç uyarmadı. Burada aranan: bir test fonksiyonunun gövdesinde
    **iki ayrı docstring** olması — tek gövdede iki docstring, yapıştırmanın
    kesin imzası.
    """
    offenders: list[str] = []
    for path in _test_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstrings = [
                stmt for stmt in node.body
                if isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ]
            if len(docstrings) > 1:
                offenders.append(
                    f"{path.name}::{node.name} ({len(docstrings)} docstring, "
                    f"satır {node.lineno})"
                )
    assert not offenders, "yapıştırılmış blok şüphesi: " + ", ".join(offenders)


def test_every_test_module_imports():
    """Sözdizimi/import hatası olan test dosyası koleksiyon hatası verir.

    `ast.parse` sözdizimini yakalar; bu test import edilebilirliği ölçer. İkisi
    ayrı: bir dosya geçerli Python olup olmayan bir isim çağırabilir.
    """
    import importlib

    broken: list[str] = []
    for path in _test_files():
        module_name = f"tests.{path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - hepsini raporlamak istiyoruz
            broken.append(f"{path.name}: {type(exc).__name__}: {exc}")
    assert not broken, "import edilemeyen test modülleri: " + "; ".join(broken)
