import json
import re

from app.script_gen import _call_llm

PITCH_PROMPT_TR = """Sen viral YouTube Shorts, TikTok ve Reels içerik stratejistisin.
Gündemdeki şu trend konuları incele:
{trends_text}

Bu trendlerden veya genel yüksek izlenme alanlarından ilham alarak izleyiciyi ekrana kilitleyecek TAM 3 FARKLI video konsepti üret:

1. Kategori: KOMEDİ / HİCİV (İş hayatı, teknoloji veya gündelik hayatın absürtlüklerine güldüren, eğlenceli ve hicivli bir kurgu)
2. Kategori: ŞAŞIRTICI BİLGİ / MERAK (İnsanların duyunca 'yok artık' diyeceği, merak uyandıran gizemli veya sarsıcı bir gerçek)
3. Kategori: MOTİVASYON / GELİŞİM (Disiplin, psikoloji, başarı veya para üzerine tokat gibi çarpan güçlü bir bakış açısı)

SADECE geçerli bir JSON listesi döndür; markdown, kod bloğu veya ekstra metin YOK. Format tam olarak şu olmalı:
[
  {{
    "id": 1,
    "category": "komedi",
    "category_label": "😂 Komedi & Hiciv",
    "title": "Kısa ve çarpıcı başlık",
    "hook": "İlk 3 saniyede söylenecek kaydırmayı durduran kanca cümle",
    "topic": "Video motoruna verilecek detaylı konu açıklaması"
  }},
  {{
    "id": 2,
    "category": "merak",
    "category_label": "🤯 Şaşırtıcı Bilgi",
    "title": "Kısa ve merak uyandıran başlık",
    "hook": "İlk 3 saniyede söylenecek kanca cümle",
    "topic": "Video motoruna verilecek detaylı konu açıklaması"
  }},
  {{
    "id": 3,
    "category": "motivasyon",
    "category_label": "🔥 Güç & Motivasyon",
    "title": "Kısa ve vurucu başlık",
    "hook": "İlk 3 saniyede söylenecek kanca cümle",
    "topic": "Video motoruna verilecek detaylı konu açıklaması"
  }}
]
"""

PITCH_PROMPT_EN = """You are a viral YouTube Shorts, TikTok, and Instagram Reels strategist.
Analyze these current trending topics:
{trends_text}

Generate EXACTLY 3 high-retention, scroll-stopping video concepts for a global audience:

1. Category: TECH & AI HACKS (Practical hidden websites, AI tools, or productivity lifehacks)
2. Category: SHOCKING CURIOSITY (Mind-blowing true facts, psychology secrets, or mysteries)
3. Category: DARK STOIC & DISCIPLINE (Powerful mental toughness, focus, self-mastery, or wealth rules)

Return ONLY a valid JSON list of 3 objects, no markdown fences, no extra text. Format:
[
  {{
    "id": 1,
    "category": "tech",
    "category_label": "💻 Tech & AI Hacks",
    "title": "Short punchy title",
    "hook": "First 3-second scroll-stopping hook",
    "topic": "Detailed prompt describing the 3 tools/ideas to generate a full script"
  }},
  {{
    "id": 2,
    "category": "curiosity",
    "category_label": "🤯 Shocking Truth",
    "title": "Short punchy title",
    "hook": "First 3-second hook",
    "topic": "Detailed topic for script generator"
  }},
  {{
    "id": 3,
    "category": "stoic",
    "category_label": "🔥 Dark Stoic / Power",
    "title": "Short punchy title",
    "hook": "First 3-second hook",
    "topic": "Detailed topic for script generator"
  }}
]
"""

FALLBACK_PITCHES_EN = [
    {
        "id": 1,
        "category": "tech",
        "category_label": "💻 Tech & AI Hacks",
        "title": "3 Insane AI Tools You Didn't Know Existed",
        "hook": "Stop wasting hours on repetitive work: these 3 free AI tools will blow your mind.",
        "topic": "Three incredible free AI websites that automate design, research, and coding tasks in seconds",
    },
    {
        "id": 2,
        "category": "curiosity",
        "category_label": "🤯 Shocking Truth",
        "title": "Why Your Brain Deceives You Every Morning",
        "hook": "The shocking psychological reason you hit the snooze button, and why it ruins your day.",
        "topic": "The science of sleep inertia and the 5-second rule that resets focus immediately",
    },
    {
        "id": 3,
        "category": "stoic",
        "category_label": "🔥 Dark Stoic / Power",
        "title": "The Rule of Unshakable Focus",
        "hook": "Marcus Aurelius had one brutal rule about people who waste your time.",
        "topic": "Stoic philosophy on ruthless time management and ignoring distractions in modern life",
    },
]

FALLBACK_PITCHES = [
    {
        "id": 1,
        "category": "komedi",
        "category_label": "😂 Komedi & Hiciv",
        "title": "Pazartesi Sabahı Çalışan Beyin",
        "hook": "Pazartesi sabahı alarm çaldığında beyninin sana oynadığı 3 büyük oyun.",
        "topic": "Pazartesi sabahı işe gitme sendromu ve çalışanların kahveyle hayata tutunma komedisi",
    },
    {
        "id": 2,
        "category": "merak",
        "category_label": "🤯 Şaşırtıcı Bilgi",
        "title": "Telefonunun Seni Dinlediğinin 3 Kanıtı",
        "hook": "Daha yeni konuştuğun o ayakkabı neden 5 dakika sonra karşına reklam olarak çıktı?",
        "topic": "Akıllı telefonların mikrofon ve veri izleme algoritmalarının nasıl çalıştığı ve şaşırtıcı gerçekler",
    },
    {
        "id": 3,
        "category": "motivasyon",
        "category_label": "🔥 Güç & Motivasyon",
        "title": "Asla Erteleme: 5 Saniye Kuralı",
        "hook": "Hayatını değiştirecek o kararı almak için beynin sana sadece 5 saniye verir.",
        "topic": "Erteleme hastalığını bitiren 5 saniye kuralı ve harekete geçmenin psikolojisi",
    },
]


def generate_pitches(trends: list[dict], api_key: str, lang: str = "tr") -> list[dict]:
    trends_text = "\n".join(
        f"- {t.get('title', '')}: {t.get('description', '')}" for t in trends[:5]
    )
    template = PITCH_PROMPT_EN if lang == "en" else PITCH_PROMPT_TR
    fallback = FALLBACK_PITCHES_EN if lang == "en" else FALLBACK_PITCHES
    prompt = template.format(trends_text=trends_text)
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = _call_llm(messages, api_key)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL)
        data = json.loads(cleaned)
        if isinstance(data, list) and len(data) >= 3:
            for item in data[:3]:
                if not all(k in item for k in ("id", "title", "hook", "topic")):
                    return fallback
            return data[:3]
    except Exception:
        pass

    return fallback

