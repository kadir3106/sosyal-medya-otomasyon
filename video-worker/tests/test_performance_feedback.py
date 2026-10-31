"""Analitik → üretim geri besleme döngüsü.

Ölçülen boşluk (düzeltme öncesi): döngü **açıktı**.

    hook hafızası okunuyor          ✅ (pipeline.py:247)
    store_winning_hook çağrısı      0
    analytics.py diske yazıyor      YOK
    topics.py performans biliyor    YOK
    boş ledger ile prompt eki       0 karakter
    elle yazılırsa                  203 karakter  <- okuma tarafı sağlamdı

Yani hafıza vardı ama hiç beslenmiyordu.
"""
import json

from app import analytics_memory, performance_ledger as pl, topics


def _write(media_dir, rows):
    (media_dir / pl.LEDGER_NAME).write_text(json.dumps(rows), encoding="utf-8")


# --- defter: yazma / tekilleştirme -------------------------------------------


def test_record_appends_and_reloads(tmp_path):
    pl.record_metrics(
        tmp_path, job_id="j1", topic="Uzay", platform="youtube",
        metrics={"views": "1000", "likes": "50"}, hook="Kimse söylemiyor",
    )

    rows = pl.load_metrics(tmp_path)

    assert len(rows) == 1
    assert rows[0]["metrics"]["views"] == "1000"
    assert rows[0]["topic"] == "Uzay"


def test_same_job_and_platform_is_refreshed_not_duplicated(tmp_path):
    """Aynı hafta iki kez rapor çekmek mükerrer satır üretmemeli."""
    for views in (100, 250):
        pl.record_metrics(
            tmp_path, job_id="j1", platform="youtube", metrics={"views": views}
        )

    rows = pl.load_metrics(tmp_path)

    assert len(rows) == 1
    assert rows[0]["metrics"]["views"] == 250


def test_record_ignores_missing_identity(tmp_path):
    pl.record_metrics(tmp_path, job_id="", platform="youtube", metrics={"views": 1})
    pl.record_metrics(tmp_path, job_id="j1", platform="", metrics={"views": 1})

    assert pl.load_metrics(tmp_path) == []


def test_load_survives_corrupt_ledger(tmp_path):
    (tmp_path / pl.LEDGER_NAME).write_text("{not json", encoding="utf-8")

    assert pl.load_metrics(tmp_path) == []


# --- defter: toplulaştırma ---------------------------------------------------


def test_topic_performance_aggregates_and_averages(tmp_path):
    _write(tmp_path, [
        {"job_id": "a", "platform": "youtube", "topic": "Uzay",
         "metrics": {"views": 1000}},
        {"job_id": "b", "platform": "youtube", "topic": "Uzay",
         "metrics": {"views": 500}},
        {"job_id": "c", "platform": "youtube", "topic": "Deniz",
         "metrics": {"views": 200}},
    ])

    stats = pl.topic_performance(tmp_path)

    assert stats["Uzay"] == {"views": 1500, "samples": 2, "avg_views": 750.0}
    assert stats["Deniz"]["views"] == 200


def test_topic_performance_accepts_plays_and_view_count(tmp_path):
    """Platformlar "izlenme" için farklı alan adları kullanıyor."""
    _write(tmp_path, [
        {"job_id": "a", "platform": "instagram", "topic": "T",
         "metrics": {"plays": 300}},
        {"job_id": "b", "platform": "x", "topic": "T",
         "metrics": {"view_count": "1,200"}},
    ])

    assert pl.topic_performance(tmp_path)["T"]["views"] == 1500


def test_topic_performance_skips_rows_without_topic(tmp_path):
    _write(tmp_path, [{"job_id": "a", "platform": "youtube", "metrics": {"views": 9}}])

    assert pl.topic_performance(tmp_path) == {}


def test_best_hooks_ranks_by_views(tmp_path):
    _write(tmp_path, [
        {"job_id": "a", "platform": "youtube", "hook": "Zayıf", "metrics": {"views": 10}},
        {"job_id": "b", "platform": "youtube", "hook": "Güçlü", "metrics": {"views": 900}},
    ])

    ranked = pl.best_hooks(tmp_path)

    assert [h["hook"] for h in ranked] == ["Güçlü", "Zayıf"]



# --- hafıza: ölçülen hook'lar prompt'a giriyor --------------------------------


def test_memory_context_is_non_empty_when_metrics_exist(tmp_path):
    """Asıl regresyon: hafıza beslenmediği için prompt eki hep 0 karakterdi."""
    _write(tmp_path, [
        {"job_id": "a", "platform": "youtube", "hook": "Ölçülmüş açılış",
         "metrics": {"views": 5000}},
    ])

    context = analytics_memory.format_hook_memory_context(tmp_path)

    assert "Ölçülmüş açılış" in context
    assert len(context) > 50


def test_memory_merges_manual_and_measured_hooks(tmp_path):
    (tmp_path / analytics_memory.DEFAULT_LEDGER_NAME).write_text(
        json.dumps({"hooks": [{"hook": "Elle işaretlenen"}]}), encoding="utf-8"
    )
    _write(tmp_path, [
        {"job_id": "a", "platform": "youtube", "hook": "Ölçülen", "metrics": {"views": 100}},
    ])

    hooks = [h["hook"] for h in analytics_memory.load_winning_hooks(tmp_path)]

    assert "Elle işaretlenen" in hooks
    assert "Ölçülen" in hooks


def test_memory_does_not_duplicate_same_hook(tmp_path):
    (tmp_path / analytics_memory.DEFAULT_LEDGER_NAME).write_text(
        json.dumps({"hooks": [{"hook": "Aynı"}]}), encoding="utf-8"
    )
    _write(tmp_path, [
        {"job_id": "a", "platform": "youtube", "hook": "aynı", "metrics": {"views": 1}},
    ])

    hooks = [h["hook"].lower() for h in analytics_memory.load_winning_hooks(tmp_path)]

    assert hooks.count("aynı") == 1


def test_memory_empty_when_no_data(tmp_path):
    assert analytics_memory.load_winning_hooks(tmp_path) == []
    assert analytics_memory.format_hook_memory_context(tmp_path) == ""


def test_store_winning_hook_writes_atomically(tmp_path):
    analytics_memory.store_winning_hook("Yeni hook", topic="T", job_id="j", media_dir=tmp_path)

    stored = json.loads(
        (tmp_path / analytics_memory.DEFAULT_LEDGER_NAME).read_text(encoding="utf-8")
    )

    assert stored["hooks"][0]["hook"] == "Yeni hook"



# --- konu seçimi: performans sıralaması --------------------------------------


def _pool(tmp_path, topics_list):
    p = tmp_path / "topics.json"
    p.write_text(json.dumps(topics_list), encoding="utf-8")
    return str(p)


def test_topic_selection_unchanged_without_ledger(tmp_path):
    """Ölçüm yoksa davranış birebir aynı kalmalı (geriye dönük uyum)."""
    path = _pool(tmp_path, ["A", "B", "C"])

    chosen = topics.select_next_topic(path, str(tmp_path / "state.json"))

    assert chosen == "A"


def test_topic_selection_boosts_proven_topic(tmp_path):
    """Kanıtlanmış performans öne geçmeli."""
    path = _pool(tmp_path, ["A", "B", "C"])
    _write(tmp_path, [
        {"job_id": "1", "platform": "youtube", "topic": "C", "metrics": {"views": 900}},
        {"job_id": "2", "platform": "youtube", "topic": "C", "metrics": {"views": 800}},
    ])

    chosen = topics.select_next_topic(
        path, str(tmp_path / "state.json"), media_dir=str(tmp_path)
    )

    assert chosen == "C"


def test_topic_selection_ignores_single_sample(tmp_path):
    """Tek video şansı sıralamayı belirlememeli (örneklem eşiği)."""
    path = _pool(tmp_path, ["A", "B"])
    _write(tmp_path, [
        {"job_id": "1", "platform": "youtube", "topic": "B", "metrics": {"views": 99999}},
    ])

    chosen = topics.select_next_topic(
        path, str(tmp_path / "state.json"), media_dir=str(tmp_path)
    )

    assert chosen == "A"


def test_topic_selection_does_not_starve_unmeasured_topics(tmp_path):
    """Ölçülmemiş konular sonsuza dek geride kalmamalı."""
    path = _pool(tmp_path, ["A", "Yeni"])
    _write(tmp_path, [
        {"job_id": "1", "platform": "youtube", "topic": "A", "metrics": {"views": 900}},
        {"job_id": "2", "platform": "youtube", "topic": "A", "metrics": {"views": 900}},
    ])
    state = str(tmp_path / "state.json")

    first = topics.select_next_topic(path, state, media_dir=str(tmp_path))
    second = topics.select_next_topic(path, state, media_dir=str(tmp_path))

    assert first == "A"
    assert second == "Yeni"


def test_topic_selection_survives_broken_ledger(tmp_path):
    path = _pool(tmp_path, ["A", "B"])
    (tmp_path / pl.LEDGER_NAME).write_text("{broken", encoding="utf-8")

    chosen = topics.select_next_topic(
        path, str(tmp_path / "state.json"), media_dir=str(tmp_path)
    )

    assert chosen == "A"
