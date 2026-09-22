import json
import logging
import os
import re

from app.config import config
from app.http_client import session

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# airouter-safe default when OPENROUTER_MODEL is unset. OpenRouter :free ids
# (e.g. google/gemma-4-31b-it:free) are rejected by airouter with HTTP 400.
DEFAULT_MODEL = "gemini-flash"
REQUIRED_KEYS = ("script", "title", "description", "tags")

# Homogeneous free-model openers — refuse / diversify away from these.
BANNED_HOOK_PREFIXES = (
    "nobody tells you",
    "the elite secretly",
    "what they don't want you to know",
    "did you know",
    "here's the thing",
)

# LLM endpoint + model .env üzerinden değiştirilebilir:
#   LLM_API_URL      -> kendi LiteLLM/openai-compatible gateway'ine yönlendirmek için
#                       (örn. http://host.docker.internal:20128/v1)
#   OPENROUTER_MODEL -> primary model (boşsa DEFAULT_MODEL); compose MUST pass it
#   OPENROUTER_MODEL_SECONDARY / OPENROUTER_MODEL_FALLBACK -> waterfall
def _resolve_url(raw: str | None) -> str:
    url = raw or DEFAULT_API_URL
    if os.path.exists("/.dockerenv") and ("127.0.0.1" in url or "localhost" in url):
        url = url.replace("://127.0.0.1:", "://host.docker.internal:").replace("://localhost:", "://host.docker.internal:")
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


OPENROUTER_URL = _resolve_url(config.LLM_API_URL)
MODEL = config.OPENROUTER_MODEL or DEFAULT_MODEL


def _model_waterfall() -> list[str]:
    """Primary → secondary → free fallback; de-dupe while preserving order."""
    models: list[str] = []
    for candidate in (
        config.OPENROUTER_MODEL or DEFAULT_MODEL,
        getattr(config, "OPENROUTER_MODEL_SECONDARY", "") or "",
        getattr(config, "OPENROUTER_MODEL_FALLBACK", "") or DEFAULT_MODEL,
    ):
        name = (candidate or "").strip()
        if name and name not in models:
            models.append(name)
    return models or [DEFAULT_MODEL]

PROMPT_TEMPLATE = """# Role & Persona
You are the elite, world-class Senior Content Director, Master Copywriter, and Crowd Psychology Expert behind accounts reaching billions of views in the PeakMotivation, Alex Hormozi style: luxury, power dynamics, wealth psychology, and modern stoicism.
Your mission: produce high-retention video scripts that hook in the first 2 seconds, hold the viewer until the final frame, and drive explosive engagement, comments, and saves across TikTok, Instagram Reels, and YouTube Shorts.

# Target Niche & Core Themes
* Niche: Luxury Lifestyle, Wealth Psychology, High-Value Power Dynamics, Modern Stoicism.
* Target Audience: Status-driven, ambitious seekers of financial freedom and unwritten elite rules (ages 18-35).
* Topic: "{topic}".

# The 4-Step Viral Blueprint (Strict Execution):
1. HOOK (0 - 3s, first 7-10 words):
   - Immediate cognitive disruption or forbidden paradox that challenges common assumptions.
   - NEVER use greetings ("Hello", "Did you know"). Drop the viewer straight into the fire.
   - FORBIDDEN template openers: "Nobody tells you…", "The elite secretly…", "What they don't want you to know…".
   - Generate 2–3 DISTINCT PeakMotivation / Hormozi-style curiosity hooks (different angles: ownership paradox, access gate, invisible rule). Put them in hook_alternatives; open the script with the strongest one.
2. BUILD-UP / TENSION (3 - 15s):
   - An untold rule, psychological mechanism, or high-stakes mystery.
   - Short, punchy, rhythmic sentences. Breathless pacing that gives the viewer zero excuse to swipe.
3. VALUE / PLOT TWIST (15 - 22s):
   - Reveal the underlying lesson or true power dynamic ("Amateurs think money buys freedom; the elite use rules to control access.").
4. CALL TO ACTION / RETENTION LOOP (22 - 25s):
   - A polarized debate question or an infinite loop where the last phrase flows naturally back into the opening hook sentence.

# Algorithm Specifications:
- Total voiceover script length MUST be strictly 55-65 words (approx. 22-25 seconds total).
- High information density, zero corporate fluff.

Return ONLY a valid JSON object with these exact keys, no markdown fences:
{{
  "hook_alternatives": ["2-3 distinct curiosity hooks (7-14 words each), different angles — no shared template opener"],
  "script": "the 55-65 word narration script; MUST start with the chosen hook from hook_alternatives",
  "title": "high-CTR curiosity title under 48 chars",
  "description": "1 punchy teaser sentence + 3 hashtags",
  "pinned_comment": "polarized debate-igniting question under 18 words",
  "tags": ["5-7", "viral", "niche", "tags"],
  "visual_prompts": [
    "ONE cinematic 9:16 vertical prompt per sentence (8-12). MUST name concrete topic subjects (e.g. Rolex crown logo, Swiss Alps vault, Geneva watchmaker bench) — never generic 'luxury lifestyle'. Dark Wealth / old-money chiaroscuro, English only."
  ],
  "visual_keywords": ["5 topic-specific English search terms, not generic wealth/luxury"],
  "concrete_nouns": ["4-8 concrete nouns/proper names from the topic for Flux prompts, e.g. Rolex, crown, vault, Geneva"],
  "scene_stock_queries": [
    {{
      "query": "ONE concrete searchable visual (3-6 English nouns). Prefer a single object people recognize instantly — e.g. 'engagement ring price tag jewelry counter' NOT 'diamond luxury lifestyle'. Keep full brand names (De Beers, Rolex).",
      "mode": "watchmaking|finance_docs|vault|chart|boardroom|diamond|generic"
    }}
  ]
}}

# scene_stock_queries RULES (critical for B-roll match):
- One object per script sentence (same order as narration). Length = number of sentences (typically 4-8).
- EACH query = ONE visual promise (what the eye should see in 1 second).
  * "tax-free Swiss trust" → "swiss bank vault legal contract papers"
  * "watchmaker / Rolex craft" → "watchmaker loupe mechanical watch gears"
  * "engagement ring worthless" → "diamond engagement ring price tag close-up"
  * "De Beers cartel / scarcity" → "De Beers diamond vault trays inventory"
  * "shareholders / stocks" → "stock market chart trading monitor"
- NEVER strip brand particles: write "De Beers" not "Beers".
- Ban irrelevant B-roll: construction, random streets, crowds, gyms, food, beaches, romantic couple filler.
"""

PROMPT_TEMPLATE_TR = """# Rol ve Kimlik
PeakMotivation ve Alex Hormozi tarzında; lüks, güç dinamikleri, servet psikolojisi ve modern stoisizm alanında milyarlarca izlenmeye ulaşan hesapların kıdemli içerik direktörü ve kitle psikolojisi uzmanısın.
Amacın: TikTok, Instagram Reels ve YouTube Shorts'ta ilk 2 saniyede izleyiciyi yakalayan (hook), sonuna kadar tutan (retention) ve yüksek yorum/kaydetme getiren video senaryoları üretmek.

# Hedef Kitle ve Niş:
* Niş: Lüks Yaşam Tarzı, Para Psikolojisi, Güç Dinamikleri, Modern Stoisizm.
* Hedef Kitle: Statü ve finansal özgürlük peşindeki hırslı kitle (18-35 yaş).
* Konu: "{topic}".

# 4 Aşamalı Viral Kurgu Formülü:
1. HOOK (0 - 3 sn): Bilişsel çelişki yaratan, ezber bozan ilk cümle. Selamlama asla yok, direkt şok.
   Yasak kalıplar: "Kimse sana söylemez…", "Nobody tells you…", "The elite secretly…".
   2–3 FARKLI merak kancası üret (hook_alternatives); script'i en güçlüsüyle aç.
2. BUILD-UP / TENSION (3 - 15 sn): Gizemli mekanizma, kısa ve vurucu cümleler, nefessiz tempo.
3. VALUE / PLOT TWIST (15 - 22 sn): Olayın arkasındaki gerçek dünya kuralı ve güç dinamiği ifşası.
4. RETENTION LOOP / CTA (22 - 25 sn): İzleyiciyi yorumlarda tartışmaya iten veya başa saran döngüsel bitiş.

- Metin KESİNLİKLE 50-60 kelime olmalı (22-25 saniye ses süresi).

SADECE şu anahtarlara sahip geçerli bir JSON nesnesi döndür:
{{
  "hook_alternatives": ["2-3 farklı merak kancası (7-14 kelime), aynı kalıp açılış yok"],
  "script": "50-60 kelimelik 4 aşamalı sesli anlatım; hook_alternatives'tan seçilen kanca ile başlamalı",
  "title": "48 karakterden kısa merak uyandırıcı başlık",
  "description": "1 cümlelik merak uyandıran açıklama + 3 hashtag",
  "pinned_comment": "yorumlarda tartışma çıkaracak 18 kelimeden kısa soru",
  "tags": ["5-7", "hedef", "etiket"],
  "visual_prompts": ["8-12 sinematik dikey prompt; konuya özgü somut nesne/mekan (Rolex, İsviçre kasası vb.) — genel 'lüks yaşam' yasak; Dark Wealth / old-money"],
  "visual_keywords": ["5 konuya özgü İngilizce arama terimi, generic wealth/luxury değil"],
  "concrete_nouns": ["4-8 somut isim / özel isim (Rolex, kasa, Cenevre vb.) Flux promptları için"],
  "scene_stock_queries": [
    {{
      "query": "o cümleye nokta atışı İngilizce stok arama terimleri (örn. swiss bank vault legal documents / watchmaker loupe gears)",
      "mode": "watchmaking|finance_docs|vault|chart|boardroom|generic"
    }}
  ]
}}

# scene_stock_queries: her cümle için 1 obje; inşaat/sokak/kalabalık B-roll yasak; finans→chart/belge, saat→ustalık/mekanizma.
"""

_TEMPLATES = {"en": PROMPT_TEMPLATE, "tr": PROMPT_TEMPLATE_TR}


def generate_script(
    topic: str,
    api_key: str,
    lang: str = "en",
    winning_context: str | None = None,
) -> dict:
    template = _TEMPLATES.get(lang, PROMPT_TEMPLATE)
    prompt_text = template.format(topic=topic)

    if winning_context:
        prompt_text += f"\n{winning_context}"

    messages = [{"role": "user", "content": prompt_text}]

    content, used_model = _call_llm_with_fallback(messages, api_key)
    try:
        data = _parse(content)
    except ValueError:
        # JSON salvage failed — one stricter retry on the same waterfall.
        strict_messages = messages + [
            {
                "role": "user",
                "content": (
                    "Your previous reply was not valid JSON. "
                    "Return ONLY a single valid JSON object with keys "
                    "hook_alternatives, script, title, description, pinned_comment, tags, "
                    "visual_prompts, visual_keywords, concrete_nouns, scene_stock_queries. No markdown."
                ),
            }
        ]
        content, used_model = _call_llm_with_fallback(strict_messages, api_key)
        data = _parse(content)
    # Re-normalize with topic so Rolex/Swiss anchors land in derived queries.
    from app.stock_media import normalize_scene_stock_queries

    data["scene_stock_queries"] = normalize_scene_stock_queries(
        data.get("scene_stock_queries"),
        script=data.get("script") or "",
        topic=topic,
        visual_prompts=data.get("visual_prompts") or [],
        visual_keywords=data.get("visual_keywords") or [],
    )
    logger.info("script_gen model used: %s", used_model)

    # Emniyet kemeri: model sınırı aştıysa bir kez kısaltma iste.
    if len(data.get("script", "").split()) > 65:
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Too long. The script is too long. Please shorten it strictly to 50-58 words. "
                    "Keep the intense hook, the identity CTA, and the seamless loop ending. "
                    "Return ONLY the updated valid JSON object."
                ),
            }
        )
        try:
            content2, _ = _call_llm_with_fallback(messages, api_key)
            try:
                data2 = _parse(content2)
                data = data2
            except Exception:
                # Model sadece düz metin olarak kısaltılmış scripti döndüyse:
                cleaned_text = content2.strip().strip('"').strip("'")
                if len(cleaned_text.split()) >= 35:
                    data["script"] = cleaned_text
        except Exception as exc:
            logger.warning("Senaryo kısaltma adımında hata (orijinal korunuyor): %s", exc)

    data["scene_stock_queries"] = normalize_scene_stock_queries(
        data.get("scene_stock_queries"),
        script=data.get("script") or "",
        topic=topic,
        visual_prompts=data.get("visual_prompts") or [],
        visual_keywords=data.get("visual_keywords") or [],
    )
    _apply_hook_alternatives(data)
    _validate_script_shape(data)
    return data


def _is_banned_hook(text: str) -> bool:
    lower = (text or "").strip().lower()
    return any(lower.startswith(prefix) for prefix in BANNED_HOOK_PREFIXES)


def _normalize_hook_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or _is_banned_hook(text):
            continue
        if text.lower() not in {o.lower() for o in out}:
            out.append(text)
    return out[:3]


def _script_opening(script: str) -> str:
    if not script:
        return ""
    return re.split(r"(?<=[.!?])\s+", script.strip(), maxsplit=1)[0].strip()


def _apply_hook_alternatives(data: dict) -> None:
    """Ensure 2–3 curiosity hooks; pick one; rewrite banned openings; keep A/B meta."""
    from app.analytics_memory import pick_hook_alternative

    alts = _normalize_hook_list(data.get("hook_alternatives"))
    script = (data.get("script") or "").strip()
    opening = _script_opening(script)

    if opening and not _is_banned_hook(opening):
        if opening.lower() not in {a.lower() for a in alts}:
            alts.insert(0, opening)
            alts = alts[:3]

    if len(alts) < 2:
        title = (data.get("title") or "").strip()
        if title and title.lower() not in {a.lower() for a in alts}:
            candidate = title if title.endswith("?") else f"Why {title} still owns the room."
            if not _is_banned_hook(candidate):
                alts.append(candidate)
        nouns = [
            n.strip()
            for n in (data.get("concrete_nouns") or [])
            if isinstance(n, str) and n.strip()
        ]
        if nouns and len(alts) < 2:
            alts.append(
                f"Everyone thinks they know {nouns[0]}. The ownership chart says otherwise."
            )
        alts = _normalize_hook_list(alts) or [a for a in alts if a][:3]

    chosen = pick_hook_alternative(alts) or (alts[0] if alts else opening)

    if chosen and script and _is_banned_hook(opening):
        rest = script[len(opening) :].lstrip(" .") if opening else script
        data["script"] = f"{chosen} {rest}".strip()

    data["hook_alternatives"] = alts[:3] if alts else ([chosen] if chosen else [])
    data["hook_selected"] = chosen or (
        data["hook_alternatives"][0] if data["hook_alternatives"] else ""
    )


def _call_llm_with_fallback(messages: list[dict], api_key: str) -> tuple[str, str]:
    """Try each model in the waterfall; auth/billing hard-fails immediately."""
    from app.errors import FalAuthBillingError

    last_exc: Exception | None = None
    for model in _model_waterfall():
        try:
            return _call_llm(messages, api_key, model=model), model
        except FalAuthBillingError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM model %s failed: %s", model, exc)
    assert last_exc is not None
    raise last_exc


def _call_llm(messages: list[dict], api_key: str, model: str | None = None) -> str:
    import requests
    from app.errors import FalAuthBillingError

    response = session.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model or MODEL, "messages": messages},
        timeout=60,
    )
    # LLM 401/402/403 / billing → hard-fail (no silent junk script → stock video).
    status = getattr(response, "status_code", None)
    raw_text = getattr(response, "text", None)
    body = raw_text[:400] if isinstance(raw_text, str) else ""
    if isinstance(status, int) and status in (401, 402, 403):
        raise FalAuthBillingError(
            f"LLM auth/billing: HTTP {status}",
            status_code=status,
            detail=body,
        )
    if body and any(
        m in body.lower()
        for m in (
            "insufficient credits",
            "payment required",
            "user is locked",
            "exhausted balance",
            "invalid api key",
            "unauthorized",
        )
    ):
        raise FalAuthBillingError(
            f"LLM auth/billing: HTTP {status}",
            status_code=status if isinstance(status, int) else None,
            detail=body,
        )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _validate_script_shape(data: dict) -> None:
    """Light structural checks without breaking JSON salvage paths."""
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"Model response missing required key '{key}': {data!r}")
    if not isinstance(data.get("script"), str) or not data["script"].strip():
        raise ValueError(f"Model response has empty script: {data!r}")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError(f"Model response has empty title: {data!r}")
    if not isinstance(data.get("tags"), list):
        raise ValueError(f"Model response tags must be a list: {data!r}")


def _parse(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.DOTALL)

    try:
        data = json.loads(cleaned, strict=False)
    except json.JSONDecodeError as exc:
        # LLM çıktılarında sıkça görülen sözdizimi hatalarını onarmayı dene:
        # 1) JSON bloğunu çevreleyen metin varsa {...} bloğunu çıkar
        match = re.search(r"(\{[\s\S]*\})", cleaned)
        candidate = match.group(1) if match else cleaned

        # 2) Satır sonlarındaki unutulmuş virgülleri onar ("değer"\n  "anahtar":)
        candidate = re.sub(
            r'("(?:\\.|[^"\\])*"|[\d\]\}\w]+)\s*\n(\s*"(?:\\.|[^"\\])*"\s*:)',
            r"\1,\n\2",
            candidate,
        )
        # 3) Kapanış parantezlerinden önceki fazla virgülleri temizle (,})
        candidate = re.sub(r",\s*([\]\}])", r"\1", candidate)

        # 4) Dizi/obje kapanışındaki bozuk tek tırnak veya kaçış karakterlerini onar (örn: 'unreal\'] -> "unreal"])
        candidate = re.sub(r'\"([^\"\n\r]*?)[\'\\]+(\s*[\]\}])', r'"\1"\2', candidate)

        try:
            data = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            # 5) Son çare: regex ile zorunlu alanları doğrudan metinden ayıkla
            data = {}
            for field in ("script", "title", "description", "pinned_comment"):
                m = re.search(rf'"{field}"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned)
                if m:
                    data[field] = m.group(1).replace(r'\"', '"').replace(r"\'", "'")
            m_tags = re.search(r'"tags"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
            if m_tags:
                data["tags"] = [t.strip().strip('"\'') for t in m_tags.group(1).split(",") if t.strip().strip('"\'')]
            m_prompts = re.search(r'"visual_prompts"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
            if m_prompts:
                data["visual_prompts"] = [p.strip().strip('"\'') for p in re.findall(r'"((?:\\.|[^"\\])*)"', m_prompts.group(1)) if p.strip()]
            m_nouns = re.search(r'"concrete_nouns"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
            if m_nouns:
                data["concrete_nouns"] = [
                    t.strip().strip("\"'")
                    for t in re.findall(r'"((?:\\.|[^"\\])*)"', m_nouns.group(1))
                    if t.strip()
                ]
            m_hooks = re.search(r'"hook_alternatives"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
            if m_hooks:
                data["hook_alternatives"] = [
                    t.strip().strip("\"'")
                    for t in re.findall(r'"((?:\\.|[^"\\])*)"', m_hooks.group(1))
                    if t.strip()
                ]

            if not data.get("script") or not data.get("title"):
                raise ValueError(f"Model returned invalid JSON: {content!r}") from exc

    # visual_keywords / concrete_nouns / scene_stock_queries optional — derive if missing.
    if "concrete_nouns" in data and not isinstance(data["concrete_nouns"], list):
        data["concrete_nouns"] = []
    if not data.get("concrete_nouns"):
        # Derive from topic-ish fields so Flux prompts stay anchored.
        from app.stock_media import prompt_concrete_terms

        derived: list[str] = []
        for src in (
            " ".join(data.get("visual_prompts") or []),
            data.get("title") or "",
            data.get("script") or "",
        ):
            for term in prompt_concrete_terms(src, max_terms=4):
                if term.lower() not in {d.lower() for d in derived}:
                    derived.append(term)
        data["concrete_nouns"] = derived[:8]

    from app.stock_media import normalize_scene_stock_queries

    data["scene_stock_queries"] = normalize_scene_stock_queries(
        data.get("scene_stock_queries"),
        script=data.get("script") or "",
        topic="",  # filled by caller if needed; derive from script alone here
        visual_prompts=data.get("visual_prompts") or [],
        visual_keywords=data.get("visual_keywords") or [],
    )

    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"Model response missing required key '{key}': {data!r}")

    return data
