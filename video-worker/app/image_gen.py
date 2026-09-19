import json
import re

from app.http_client import session
from app.script_gen import MODEL, OPENROUTER_URL

PROMPT_TEMPLATE = """You are writing a short Turkish image-post for a faceless \
social media brand about: "{topic}"

Return ONLY a JSON object with these exact keys, no markdown fences, no extra text:
{{
  "text": "a single curiosity-driven fact or insight about the topic, 50-100 characters, written for a square image card",
  "caption": "1-2 sentence caption in Turkish with 3-5 relevant hashtags",
  "hashtags": ["list", "of", "3-5", "hashtags", "without", "the", "#"]
}}"""


def generate_image_content(topic: str, api_key: str) -> dict:
    response = session.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(topic=topic)}],
        },
        timeout=60,
    )
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.DOTALL)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {content!r}") from exc

    for key in ("text", "caption", "hashtags"):
        if key not in data:
            raise ValueError(f"Model response missing required key '{key}': {data!r}")

    return data


from PIL import Image, ImageDraw, ImageFont

# Türkçe karakter destekli font zinciri: Pillow'un gömülü DejaVuSans'ı
# (Pillow >= 10) her ortamda garanti çalışır; Windows'ta arial tercih edilir.
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
]

CARD_SIZE = (1080, 1080)
BACKGROUND = "#0F172A"
FOOTER_TEXT = "Bu içerik AI tarafından üretildi"


def _load_font(size: int):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(
    text: str, brand_name: str, accent: str, output_path: str, footer: str = FOOTER_TEXT
) -> str:
    image = Image.new("RGB", CARD_SIZE, color=BACKGROUND)
    draw = ImageDraw.Draw(image)

    font_brand = _load_font(64)
    font_text = _load_font(72)
    font_footer = _load_font(32)

    draw.text(
        (540, 160), brand_name, fill=accent, font=font_brand, anchor="mm"
    )

    lines = _wrap_text(draw, text[:160], font_text, max_width=880)
    line_height = 96
    total_height = line_height * len(lines)
    start_y = 540 - total_height // 2 + line_height // 2
    for index, line in enumerate(lines):
        draw.text(
            (540, start_y + index * line_height),
            line,
            fill="white",
            font=font_text,
            anchor="mm",
        )

    draw.text(
        (540, 960), footer, fill="#64748B", font=font_footer, anchor="mm"
    )

    image.save(output_path, format="PNG")
    return output_path
