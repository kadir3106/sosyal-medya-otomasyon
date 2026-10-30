"""Script quality + fact verification regression tests (requirements 1–17)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.fact_verify import FactVerificationProvider, VerificationResult
from app.script_claims import classify_sentence, extract_claims
from app.script_quality import (
    apply_decisions_to_script,
    batch_quality_edit,
    decide_claims,
    linguistic_quality_issues,
    merge_into_script_dict,
    refine_script,
)


# ---------------------------------------------------------------------------
# 1–4 claim extraction / risk
# ---------------------------------------------------------------------------


def test_exact_numerical_claim_requires_verification():
    claims = extract_claims(
        "Rolex transferred 100% ownership in 1960.",
        topic="Rolex",
    )
    assert claims
    assert any(c.verification_required for c in claims)
    assert any(c.risk == "HIGH" for c in claims)
    assert any(c.claim_type in {"numerical", "ownership", "historical", "financial"} for c in claims)


def test_tax_legal_claim_is_high_risk():
    ctype, risk, _, need = classify_sentence(
        "Rolex channels profits tax-free into Swiss charities.",
        topic="Rolex",
    )
    assert ctype in {"tax", "legal", "financial"}
    assert risk == "HIGH"
    assert need is True


def test_ownership_claim_requires_verification():
    claims = extract_claims(
        "The Hans Wilsdorf Foundation owns Rolex.",
        topic="Rolex",
    )
    assert any(c.claim_type == "ownership" for c in claims)
    assert any(c.verification_required for c in claims)


def test_rhetorical_sentence_skips_verification():
    claims = extract_claims("Real power moves quietly.", topic="Rolex")
    assert claims
    assert all(c.claim_type == "opinion_rhetorical" for c in claims)
    assert all(not c.verification_required for c in claims)
    assert all(c.risk == "LOW" for c in claims)


# ---------------------------------------------------------------------------
# 5–8 claim decisions + editor discipline
# ---------------------------------------------------------------------------


def test_unsupported_high_claim_removed():
    from app.script_claims import ScriptClaim

    c = ScriptClaim(
        claim_id="a1",
        text="Rolex controls the entire global luxury market.",
        claim_type="ownership",
        risk="HIGH",
        verification_required=True,
    )
    v = VerificationResult(claim_id="a1", status="unsupported", confidence=0.8)
    decisions = decide_claims([c], [v])
    assert decisions[0].action == "remove"
    out = apply_decisions_to_script(c.text, decisions)
    assert "entire global luxury market" not in out.lower()


def test_partially_supported_claim_softened():
    from app.script_claims import ScriptClaim

    c = ScriptClaim(
        claim_id="b1",
        text="Rolex channels billions tax-free into Swiss foundations.",
        claim_type="tax",
        risk="HIGH",
        verification_required=True,
    )
    v = VerificationResult(claim_id="b1", status="partially_supported", confidence=0.5)
    decisions = decide_claims([c], [v])
    assert decisions[0].action == "soften"
    assert decisions[0].rewritten
    soft = decisions[0].rewritten.lower()
    assert "tax-free" not in soft
    assert "billions" not in soft


def test_verified_claim_preserved():
    from app.script_claims import ScriptClaim

    text = "The Hans Wilsdorf Foundation owns Rolex."
    c = ScriptClaim(
        claim_id="c1",
        text=text,
        claim_type="ownership",
        risk="MEDIUM",
        verification_required=True,
    )
    v = VerificationResult(claim_id="c1", status="supported", confidence=0.9)
    decisions = decide_claims([c], [v])
    assert decisions[0].action == "keep"
    out = apply_decisions_to_script(text, decisions)
    assert "Hans Wilsdorf Foundation" in out


def test_editor_cannot_strengthen_evidence():
    draft = "The Hans Wilsdorf Foundation owns Rolex."
    banned = ["Rolex channels billions tax-free"]
    final, _, _, _ = batch_quality_edit(
        draft,
        topic="Rolex",
        allowed_facts=[draft],
        banned_strengthen=banned,
        target_words=40,
    )
    # With LLM_API_URL possibly set, still must not reintroduce banned strength
    assert "tax-free" not in final.lower()
    assert "billions" not in final.lower()
    # Simulate strengthened LLM output rejection path
    from app.script_quality import _editor_strengthened

    assert _editor_strengthened(
        "Rolex channels billions tax-free into Swiss banks.",
        banned,
        draft,
    )


# ---------------------------------------------------------------------------
# 9–12 linguistic + hook + loop
# ---------------------------------------------------------------------------


def test_incomplete_clause_rejected():
    issues = linguistic_quality_issues("Founder Hans Wilsdorf locked 100%.")
    assert any(
        i.startswith(("incomplete_clause", "missing_verb")) for i in issues
    )
    result = refine_script(
        "Founder Hans Wilsdorf locked 100%. Real power moves quietly.",
        topic="Rolex",
        skip_llm_edit=True,
        verifier=_StubVerifier(status="unsupported"),
    )
    assert "locked 100%" not in result.final_script.lower()


def test_natural_spoken_sentence_accepted():
    issues = linguistic_quality_issues(
        "The Hans Wilsdorf Foundation owns Rolex today."
    )
    assert issues == []


def test_hook_factual_claim_goes_through_verification():
    raw = (
        "In 1960 Rolex had no shareholders. "
        "The Hans Wilsdorf Foundation owns the company. "
        "Real power moves quietly."
    )
    result = refine_script(
        raw,
        topic="Rolex",
        skip_llm_edit=True,
        verifier=_StubVerifier(status_map={
            "no shareholders": "unsupported",
            "Foundation owns": "supported",
        }),
    )
    assert "no shareholders" not in result.final_script.lower() or "public" in result.final_script.lower()
    # Hook should not reintroduce removed unsupported scandal framing as absolute
    assert "tax-free" not in (result.hook or "").lower()


def test_bad_loop_rejected():
    result = refine_script(
        "The Hans Wilsdorf Foundation owns Rolex. Amateurs chase flips.",
        topic="Rolex",
        skip_llm_edit=True,
        verifier=_StubVerifier(status="supported"),
    )
    assert result.final_script.endswith((".", "!", "?"))
    assert "force" not in (result.loop_strategy or "").lower()


# ---------------------------------------------------------------------------
# 13–14 fail-closed + TTS gets final_script
# ---------------------------------------------------------------------------


def test_verification_outage_fail_closed():
    class Boom(FactVerificationProvider):
        def verify_claims(self, claims, *, topic=""):
            raise RuntimeError("network down")

    raw = (
        "Rolex channels billions tax-free into Swiss vaults. "
        "Real power moves quietly."
    )
    result = refine_script(raw, topic="Rolex", verifier=Boom(), skip_llm_edit=True)
    assert result.verification_outage is True
    assert "tax-free" not in result.final_script.lower()
    assert "billions" not in result.final_script.lower()
    removed = [d for d in result.claim_decisions if d.get("action") == "remove"]
    assert removed
    assert any("outage" in (d.get("reason") or "") for d in removed)


def test_downstream_tts_receives_final_script():
    raw = "Rolex controls the entire market. Real power moves quietly."
    result = refine_script(
        raw,
        topic="Rolex",
        skip_llm_edit=True,
        verifier=_StubVerifier(status="unsupported"),
    )
    script = {
        "script": raw,
        "title": "t",
        "description": "d",
        "tags": ["a"],
    }
    merged = merge_into_script_dict(script, result)
    assert merged["script"] == result.final_script
    assert merged["final_script"] == result.final_script
    assert "entire market" not in merged["script"].lower()


def test_pipeline_calls_refine_before_tts():
    """Smoke: pipeline imports refine_script and wires it (static presence)."""
    import inspect
    import app.pipeline as pipeline

    src = inspect.getsource(pipeline._generate_video_sync)
    assert "refine_script" in src
    assert "merge_into_script_dict" in src
    assert 'script_data["script"]' in src


# ---------------------------------------------------------------------------
# Stub verifier
# ---------------------------------------------------------------------------


class _StubVerifier(FactVerificationProvider):
    def __init__(self, status: str = "supported", status_map: dict | None = None):
        self.status = status
        self.status_map = status_map or {}

    def verify_claims(self, claims, *, topic=""):
        out = []
        for c in claims:
            if not c.verification_required:
                out.append(
                    VerificationResult(
                        claim_id=c.claim_id,
                        status="supported",
                        notes="skip",
                    )
                )
                continue
            st = self.status
            for needle, mapped in self.status_map.items():
                if needle.lower() in c.text.lower():
                    st = mapped
                    break
            out.append(
                VerificationResult(
                    claim_id=c.claim_id,
                    status=st,
                    confidence=0.7,
                    sources=[{"title": "stub", "url": "https://example.com", "provider": "stub"}],
                    notes="stub",
                )
            )
        return out


# ---------------------------------------------------------------------------
# Phase 2 / 3 / pending unchanged — import/symbol smoke (full suites run separately)
# ---------------------------------------------------------------------------


def test_phase2_director_symbols_intact():
    from app import director, director_planner

    assert hasattr(director, "plan_and_fetch_scenes")
    assert director_planner is not None


def test_phase3_modules_intact():
    from app import audio_bgm, phase3_profiles, phase3_retention, subtitles

    assert hasattr(audio_bgm, "get_or_create_bgm")
    assert hasattr(phase3_profiles, "build_music_profile")
    assert hasattr(phase3_retention, "plan_retention_events")
    assert hasattr(subtitles, "write_ass")


def test_pending_approval_path_unchanged():
    from app import jobs as job_store
    import inspect
    import app.pipeline as pipeline

    assert hasattr(job_store, "write_pending_mirror")
    src = inspect.getsource(pipeline._generate_video_sync)
    assert "write_pending_mirror" in src
    assert "awaiting_approval" in src
