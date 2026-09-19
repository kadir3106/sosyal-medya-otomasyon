import json
import logging
import os
import re

from app.config import config
from app.http_client import session

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-31b-it:free"

# LLM endpoint + model .env üzerinden değiştirilebilir:
#   LLM_API_URL      -> kendi LiteLLM/openai-compatible gateway'ine yönlendirmek için
#                       (örn. http://host.docker.internal:4000/v1)
#   OPENROUTER_MODEL -> model adı (boşsa DEFAULT_MODEL kullanılır)
def _resolve_url(raw: str | None) -> str:
    url = raw or DEFAULT_API_URL
    if os.path.exists("/.dockerenv") and ("127.0.0.1" in url or "localhost" in url):
        url = url.replace("://127.0.0.1:", "://host.docker.internal:").replace("://localhost:", "://host.docker.internal:")
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


OPENROUTER_URL = _resolve_url(config.LLM_API_URL)
MODEL = config.OPENROUTER_MODEL or DEFAULT_MODEL

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
  "script": "the 55-65 word narration script following the 4-step blueprint",
  "title": "high-CTR curiosity title under 48 chars",
  "description": "1 punchy teaser sentence + 3 hashtags",
  "pinned_comment": "polarized debate-igniting question under 18 words",
  "tags": ["5-7", "viral", "niche", "tags"],
  "visual_prompts": [
    "ONE cinematic 9:16 vertical prompt per sentence (8-12 prompts). Specify dramatic chiaroscuro lighting, camera moves (dolly push, low angle, macro), 8k photorealistic detail, always in English."
  ],
  "visual_keywords": ["5", "cinematic", "English", "search", "terms"]
}}"""

PROMPT_TEMPLATE_TR = """# Rol ve Kimlik
PeakMotivation ve Alex Hormozi tarzında; lüks, güç dinamikleri, servet psikolojisi ve modern stoisizm alanında milyarlarca izlenmeye ulaşan hesapların kıdemli içerik direktörü ve kitle psikolojisi uzmanısın.
Amacın: TikTok, Instagram Reels ve YouTube Shorts'ta ilk 2 saniyede izleyiciyi yakalayan (hook), sonuna kadar tutan (retention) ve yüksek yorum/kaydetme getiren video senaryoları üretmek.

# Hedef Kitle ve Niş:
* Niş: Lüks Yaşam Tarzı, Para Psikolojisi, Güç Dinamikleri, Modern Stoisizm.
* Hedef Kitle: Statü ve finansal özgürlük peşindeki hırslı kitle (18-35 yaş).
* Konu: "{topic}".

# 4 Aşamalı Viral Kurgu Formülü:
1. HOOK (0 - 3 sn): Bilişsel çelişki yaratan, ezber bozan ilk cümle. Selamlama asla yok, direkt şok.
2. BUILD-UP / TENSION (3 - 15 sn): Gizemli mekanizma, kısa ve vurucu cümleler, nefessiz tempo.
3. VALUE / PLOT TWIST (15 - 22 sn): Olayın arkasındaki gerçek dünya kuralı ve güç dinamiği ifşası.
4. RETENTION LOOP / CTA (22 - 25 sn): İzleyiciyi yorumlarda tartışmaya iten veya başa saran döngüsel bitiş.

- Metin KESİNLİKLE 50-60 kelime olmalı (22-25 saniye ses süresi).

SADECE şu anahtarlara sahip geçerli bir JSON nesnesi döndür:
{{
  "script": "50-60 kelimelik 4 aşamalı sesli anlatım metni",
  "title": "48 karakterden kısa merak uyandırıcı başlık",
  "description": "1 cümlelik merak uyandıran açıklama + 3 hashtag",
  "pinned_comment": "yorumlarda tartışma çıkaracak 18 kelimeden kısa soru",
  "tags": ["5-7", "hedef", "etiket"],
  "visual_prompts": ["8-12 adet sinematik dikey görsel promptu"],
  "visual_keywords": ["5", "ingilizce", "arama", "kelimesi"]
}}"""

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

    content = _call_llm(messages, api_key)
    data = _parse(content)

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
            content2 = _call_llm(messages, api_key)
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

    return data


def _call_llm(messages: list[dict], api_key: str) -> str:
    response = session.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "messages": messages},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


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

            if not data.get("script") or not data.get("title"):
                raise ValueError(f"Model returned invalid JSON: {content!r}") from exc

    # visual_keywords kasten zorunlu tutulmuyor: model bazen bu isteğe bağlı
    # alanı atlayabilir; pipeline.py o durumda script'ten anahtar kelime
    # çıkarmaya (extract_keywords) düşüyor — bir günün tamamını bu yüzden
    # kaybetmeye değmez.
    for key in ("script", "title", "description", "tags"):
        if key not in data:
            raise ValueError(f"Model response missing required key '{key}': {data!r}")

    return data
