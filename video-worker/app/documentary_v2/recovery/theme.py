"""Documentary visual theme — style separated from factual content."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DocumentaryVisualTheme:
    theme_id: str = "documentary_cinematic_v1"
    background_top: tuple[int, int, int] = (8, 10, 16)
    background_bottom: tuple[int, int, int] = (18, 22, 34)
    accent: tuple[int, int, int] = (212, 175, 55)  # restrained gold
    text_primary: tuple[int, int, int] = (245, 245, 242)
    text_secondary: tuple[int, int, int] = (180, 185, 195)
    line: tuple[int, int, int] = (90, 95, 110)
    font_family: str = "DejaVuSans"  # PIL fallback path resolved at render
    title_size: int = 52
    body_size: int = 36
    label_size: int = 36
    line_weight: int = 2
    node_radius: int = 8
    motion_speed: float = 1.0
    easing: str = "ease_out_cubic"
    corner_radius: int = 0  # cinematic: prefer sharp / soft bleed, not card chrome
    width: int = 1080
    height: int = 1920
    fps: int = 30
    caption_safe_top: float = 0.08
    caption_safe_bottom: float = 0.30
    caption_safe_left: float = 0.06
    caption_safe_right: float = 0.06

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_THEME = DocumentaryVisualTheme()
