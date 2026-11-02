# Script Quality Baseline

**Date:** 2026-09-23  
**Scope:** Analysis only (pre–Script Quality & Fact Verification Layer)  
**Frozen:** Phase 2 visual + Phase 3/3.1/3.2 audio-retention-caption

---

## Current flow

```text
topic (topics.py / Telegram / /generate body)
  → optional analytics_memory winning_context
  → script_gen.generate_script(topic, api_key, lang)
       → PROMPT_TEMPLATE (Hormozi / PeakMotivation viral blueprint)
       → AIRouter LLM (LLM_API_URL / gemini-flash waterfall)
       → JSON parse + scene_stock_queries normalize
       → optional shorten pass if >65 words
       → hook_alternatives / banned-prefix rewrite
       → _validate_script_shape (keys only)
  → pipeline: TTS(script) → ASS → Director → Phase 3.2 render → pending
```

No intermediate research, claim extraction, fact verification, or linguistic quality editor exists today.

---

## Component findings

| Question | Answer |
|----------|--------|
| Research / source fetch before script? | **No** — topic string + optional channel analytics context only |
| Factual verification? | **No** |
| Claim extraction? | **No** |
| Second-pass editing? | Only length-shorten retry + banned-hook rewrite |
| Hallucination guard? | **No** (prompt style pushes paradox / “untold rule”) |
| Script length control? | Prompt: 55–65 words; post-check >65 → one shorten LLM call |
| Hook generation? | Prompt + `hook_alternatives`; `pick_hook_alternative`; banned prefix list |
| Loop generation? | Prompt asks seamless loop ending → opening; **no validation** that ending is grammatical |
| Downstream TTS input? | `script_data["script"]` verbatim |

---

## Prompt incentives (risk)

`PROMPT_TEMPLATE` optimizes for:

- cognitive disruption / forbidden paradox
- high information density
- polarized CTA / infinite loop
- 22–25s word budget

It does **not** require:

- citeable sources
- hedging absolute claims (`100%`, `tax-free`, `entire market`)
- grammatical completeness of compressed phrases

This explains observed Rolex drafts: strong visuals + over-compressed / over-assertive lines (“locked 100%”, “channels billions tax-free”).

---

## Validation today

`_validate_script_shape` checks presence of `script`, `title`, `description`, `tags` only.

No checks for:

- incomplete clauses
- unsupported numbers / tax / ownership absolutes
- claim strength vs evidence

---

## Integration point (planned)

Insert **after** `generate_script` returns and **before** TTS:

```text
raw_script
  → claim extraction
  → FactVerificationProvider (evidence, not AIRouter-as-oracle)
  → claim decisions
  → single-batch quality editor (AIRouter)
  → final_script → TTS / Director / Phase 3.2
```

Do not modify Director, retention, music, captions, render, publishers, or AIRouter routing.

---

## Gaps to close

1. Claim model + HIGH-risk gate  
2. Evidence-backed verification (Wikipedia / reputable refs via HTTP)  
3. Fail-closed on verification outage for HIGH claims  
4. Natural spoken English editor without strengthening claims  
5. Trace artifacts: raw / claims / evidence / decisions / final  
6. Tests + Rolex REAL E2E
