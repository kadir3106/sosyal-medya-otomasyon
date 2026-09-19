import xml.etree.ElementTree as ET
from app.http_client import session

GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"

FALLBACK_TRENDS = [
    {"title": "Yapay Zeka ve Gelecek", "description": "Yapay zekanın insan hayatını ve meslekleri dönüştürmesi"},
    {"title": "Para Yönetimi ve Zenginlik", "description": "Finansal özgürlük, yatırım ve disiplin sırları"},
    {"title": "Sosyal Medya Bağımlılığı", "description": "Dopamin döngüsü ve modern çağın dikkat dağınıklığı"},
    {"title": "Uzay ve Evrenin Gizemleri", "description": "Kara delikler ve keşfedilmemiş derin evren"},
    {"title": "Günlük Yaşamın Absürtlükleri", "description": "İş hayatı ve modern dünyanın komik çelişkileri"},
]


def fetch_trends(geo: str = "US", max_count: int = 5) -> list[dict]:
    """Google Trends RSS üzerinden en güncel arama trendlerini çeker."""
    url = GOOGLE_TRENDS_RSS_URL.format(geo=geo)
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        items = []
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            desc_elem = item.find("description")
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
            if title:
                items.append({"title": title, "description": desc})
            if len(items) >= max_count:
                break

        if items:
            return items
    except Exception:
        pass

    return FALLBACK_TRENDS[:max_count]


def get_trending_viral_topic(api_key: str, geo: str = "US") -> str:
    """Canlı trendleri çeker ve LLM ile Dark Wealth / Power Dynamics tarzında viral bir konuya dönüştürür."""
    trends = fetch_trends(geo=geo, max_count=6)
    headlines = ", ".join([f"'{t['title']}'" for t in trends])

    prompt = f"""You are a master viral trend director for YouTube Shorts and TikTok in the Dark Wealth, Money Psychology, and Power Dynamics niche.
Here are the current top real-time trending news topics: {headlines}.

Select the most money, power, corporation, psychological, or high-stakes related angle from these trends (or connect one of them to high finance / corporate greed / billionaire systems).
Transform it into ONE explosive, curiosity-provoking video topic title for a 60-second video.
Example: 'The Secret Wall Street Algorithm Behind Today's Market Panic'
Output ONLY the single topic title as plain text, no quotes, no extra words."""

    try:
        from app.config import config
        from app.script_gen import OPENROUTER_URL, MODEL
        resp = session.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=25,
        )
        if resp.status_code == 200:
            result = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'')
            if result and len(result) > 10:
                return result
    except Exception as e:
        print(f"[trends] Trend dönüştürme uyarısı: {e}")

    # Fallback to top headline or luxury scandal
    return f"The Secret Behind {trends[0]['title']}: What the Billionaires Won't Tell You"
