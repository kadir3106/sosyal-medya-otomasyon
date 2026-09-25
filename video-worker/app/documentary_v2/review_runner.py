"""Explicit, unpublished topic-to-review-MP4 path for Documentary Engine V2."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from app.audio_bgm import get_or_create_bgm
from app.config import config
from app.documentary_v2.assembly.orchestrator import StageFResult, run_stage_f_pipeline
from app.documentary_v2.beat_planner import plan_beats
from app.documentary_v2.director.pipeline import DirectorBudget
from app.documentary_v2.review_story import prepare_review_story
from app.phase3_profiles import build_music_profile
from app.subtitles import write_ass
from app.tts import synthesize_speech


MANDATORY_GATES = (
    "FactQualityGate", "StoryQualityGate", "StoryConsistencyGate", "BeatPlanGate",
    "VisualCoverageGate", "NoSlideshowQualityGate", "LicenseProvenanceGate",
    "TechnicalRenderQA", "FinalVideoQualityGate",
)

HUMAN_REVIEW = (
    "Slideshow hissi ve fotoğraf+zoom bağımlılığı",
    "Gerçek/native motion oranı",
    "Shot ile spoken beat eşleşmesi",
    "Motion graphic okunabilirliği ve kanıta bağlılığı",
    "Generic filler ve aynı asset tekrarları",
    "Caption örtüşmesi, güvenli alan ve okunabilirlik",
    "Hook, gelişme ve payoff",
    "Ritim, kesmeler ve geçişler",
    "Seslendirme ile müzik dengesi",
    "Gerçek mini-belgesel hissi",
)


def automated_verdict(gates: dict[str, str]) -> str:
    values = [gates.get(name, "NOT_RUN") for name in MANDATORY_GATES]
    if "FAIL" in values:
        return "FAIL"
    if any(value != "PASS" for value in values):
        return "REVIEW_REQUIRED"
    return "PASS"


def _save_report(result: StageFResult, media: Path, *, reasons: list[str]) -> None:
    for name in MANDATORY_GATES:
        result.gates.setdefault(name, "NOT_RUN")
    verdict = automated_verdict(result.gates)
    if result.error or not result.output_mp4:
        verdict = "FAIL"
    if result.metrics.get("director_budget_stop_reason") and verdict == "PASS":
        verdict = "REVIEW_REQUIRED"
    if not result.metrics.get("remote_vision_available") and verdict == "PASS":
        verdict = "REVIEW_REQUIRED"
    result.metrics["automated_verdict"] = verdict
    result.metrics["human_verdict"] = "NOT_RUN"
    result.publish = False

    stem = f"DOCUMENTARY_ENGINE_V2_TOPIC_REVIEW_{result.job_id}"
    summary = media / f"{stem}.json"
    report = media / f"{stem}.md"
    result.report_path = str(report)
    result.metrics["summary_path"] = str(summary)
    media.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    gate_lines = "\n".join(f"- {name}: {result.gates.get(name, 'NOT_RUN')}" for name in MANDATORY_GATES)
    checklist = "\n".join(f"- [ ] {item}" for item in HUMAN_REVIEW)
    reason_lines = "\n".join(f"- {reason}" for reason in reasons) or "- Yok"
    report.write_text(
        f"# Documentary Engine V2 — konu inceleme paketi\n\n"
        f"Konu: {result.topic}\n\n"
        f"Otomatik karar: {verdict} (yalnız insan incelemesine hazır; yayın onayı değildir)\n\n"
        f"İnsan kararı: NOT_RUN\n\nYayın: hayır\n\n"
        f"Video: {result.output_mp4 or 'oluşturulmadı'}\n\n"
        f"EDL: {result.edl_path or 'oluşturulmadı'}\n\n"
        f"Manifest: {result.manifest_path or 'oluşturulmadı'}\n\n"
        f"Atıf: {result.attribution_path or 'oluşturulmadı'}\n\n"
        f"Trace: {result.trace_path or 'oluşturulmadı'}\n\n"
        f"Doğrulanmış iddia sayısı: {len(result.metrics.get('verified_claims') or [])}\n\n"
        f"Görsel iş bütçesi: {json.dumps(result.metrics.get('director_budget') or {}, ensure_ascii=False)}\n\n"
        f"Bütçe durma nedeni: {result.metrics.get('director_budget_stop_reason') or 'yok'}\n\n"
        f"Remote görsel doğrulama anahtarı: {'var' if result.metrics.get('remote_vision_available') else 'yok'}\n\n"
        f"Hata: {result.error or 'yok'}\n\n"
        f"## Otomatik kapılar\n\n{gate_lines}\n\n"
        f"## Notlar\n\n{reason_lines}\n\n"
        f"## İnsan gözüyle inceleme\n\n{checklist}\n",
        encoding="utf-8",
    )


def run_topic_review(
    topic: str, media_dir: str | Path, *, job_id: str | None = None,
    max_job_elapsed_sec: float = 360.0,
) -> StageFResult:
    """Run the isolated review path synchronously; never call publishing systems."""
    jid = job_id or f"review_{uuid.uuid4().hex[:12]}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", jid):
        raise ValueError("job_id must be a short path-safe token")
    media = Path(media_dir)
    result = StageFResult(jid, topic.strip())
    reasons: list[str] = []
    result.metrics["remote_vision_available"] = bool(config.GROQ_API_KEY)
    if not config.GROQ_API_KEY:
        reasons.append("Direct Groq görsel doğrulama/eleştirmen anahtarı yok; remote kalite kontrolü PASS sayılamaz.")
    started = time.monotonic()
    deadline = started + max_job_elapsed_sec

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("review_job_deadline_exceeded")
        return left

    if not topic.strip():
        result.error = "empty_topic"
        result.gates["FactQualityGate"] = "FAIL"
        _save_report(result, media, reasons=["Konu boş; araştırma veya seslendirme başlatılmadı."])
        return result

    work = media / "work" / jid / "topic_review"
    try:
        if not config.OPENROUTER_API_KEY:
            raise ValueError("missing_text_llm_key")
        remaining()
        prepared = prepare_review_story(topic.strip(), config.OPENROUTER_API_KEY)
        result.script = prepared.story.final_script
        result.gates.update(prepared.gates)
        result.metrics["verified_claims"] = [claim.to_dict() for claim in prepared.claims]
        reasons.extend(prepared.reasons)

        remaining()
        beat_plan = plan_beats(topic.strip(), prepared.story.final_script, prepared.claims, config.OPENROUTER_API_KEY)
        result.beats = [beat.to_dict() for beat in beat_plan.beats]
        result.gates["BeatPlanGate"] = beat_plan.gate
        reasons.extend(beat_plan.reasons)

        work.mkdir(parents=True, exist_ok=True)
        audio_path = work / "narration.mp3"
        caption_path = work / "captions.ass"
        tts_meta: dict = {}
        remaining()
        boundaries = asyncio.run(
            asyncio.wait_for(
                synthesize_speech(prepared.story.final_script, str(audio_path), meta_out=tts_meta),
                timeout=min(120.0, remaining()),
            )
        )
        result.metrics["tts"] = tts_meta
        if not audio_path.is_file() or audio_path.stat().st_size == 0 or not boundaries:
            result.error = "missing_audio_or_captions"
            result.gates["TechnicalRenderQA"] = "FAIL"
            _save_report(result, media, reasons=reasons)
            return result

        remaining()
        write_ass(boundaries, str(caption_path), phase3=True, script_text=prepared.story.final_script)
        if not caption_path.is_file() or caption_path.stat().st_size == 0:
            result.error = "missing_audio_or_captions"
            result.gates["TechnicalRenderQA"] = "FAIL"
            _save_report(result, media, reasons=reasons)
            return result

        music = build_music_profile(topic=topic, script=prepared.story.final_script)
        music_dir = Path(config.BGM_DIR)
        selection: dict = {}
        bgm_path = None
        has_tracks = music_dir.is_dir() and (
            any(music_dir.glob("*.mp3")) or any(music_dir.glob("*.wav"))
        )
        if has_tracks:
            remaining()
            bgm_path = get_or_create_bgm(
                str(music_dir), vocals_allowed=False, prefer_instrumental=True,
                mood=music.mood, allow_silence=True, selection_out=selection,
            )
        else:
            selection["reason"] = "no_curated_music_library"
        result.metrics["music"] = {"mood": music.mood, "selection": selection, "path": bgm_path}

        remaining()
        budget = DirectorBudget(max_elapsed_sec=min(180.0, max(1.0, remaining() / 2)))
        result.metrics["director_budget"] = asdict(budget)
        assembled = run_stage_f_pipeline(
            topic=topic.strip(), script=prepared.story.final_script, claims=prepared.claims,
            media_dir=media, job_id=jid, audio_path=str(audio_path),
            word_boundaries=boundaries, caption_path=str(caption_path), bgm_path=bgm_path,
            beats=beat_plan.beats, story_gates=prepared.gates, beat_plan_gate=beat_plan.gate,
            director_budget=budget, run_critic=True, live_acquire=True, materialize=True,
            deadline_monotonic=deadline,
        )
        assembled.metrics.update(result.metrics)
        if time.monotonic() > deadline and not assembled.error:
            assembled.error = "review_job_deadline_exceeded"
        if assembled.trace_path and Path(assembled.trace_path).is_file():
            trace = json.loads(Path(assembled.trace_path).read_text(encoding="utf-8"))
            diagnostics = trace.get("director_diagnostics") or {}
            assembled.metrics["director_budget_stop_reason"] = diagnostics.get("budget_stop_reason") or ""
            if diagnostics.get("budget_stop_reason"):
                reasons.append(f"Görsel iş bütçesi durdu: {diagnostics['budget_stop_reason']}")
        result = assembled
    except Exception as exc:
        result.error = str(exc)[:500]
        result.gates.setdefault("TechnicalRenderQA", "FAIL")
        reasons.append(f"İnceleme işi tamamlanamadı: {type(exc).__name__}")

    result.metrics["elapsed_sec"] = round(time.monotonic() - started, 3)
    _save_report(result, media, reasons=reasons)
    return result
