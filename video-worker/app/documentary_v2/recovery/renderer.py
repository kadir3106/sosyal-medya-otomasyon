"""MotionGraphicRenderer — cinematic vertical clips via PIL + FFmpeg.

Remotion remains available as an optional specialized path; Stage E default
renderer is internal so Docker/worker can produce valid isolated clips without
Node. Style is documentary-minimal, caption-safe, not PowerPoint.
"""
from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.documentary_v2.recovery.theme import DEFAULT_THEME, DocumentaryVisualTheme
from app.documentary_v2.schemas import MotionGraphicPlan


@dataclass
class MotionGraphicRenderResult:
    ok: bool
    path: str = ""
    plan_id: str = ""
    duration_sec: float = 0.0
    width: int = 1080
    height: int = 1920
    fps: int = 30
    renderer: str = "internal_motion_graphics"
    content_fingerprint: str = ""
    qa: dict = None  # type: ignore
    provenance: dict = None  # type: ignore
    error: str = ""

    def __post_init__(self) -> None:
        if self.qa is None:
            self.qa = {}
        if self.provenance is None:
            self.provenance = {}


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _gradient(theme: DocumentaryVisualTheme) -> Image.Image:
    w, h = theme.width, theme.height
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    top, bot = theme.background_top, theme.background_bottom
    for y in range(h):
        t = y / max(h - 1, 1)
        col = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=col)
    return img


def _safe_box(theme: DocumentaryVisualTheme) -> tuple[int, int, int, int]:
    w, h = theme.width, theme.height
    left = int(w * theme.caption_safe_left)
    right = int(w * (1 - theme.caption_safe_right))
    top = int(h * theme.caption_safe_top)
    bottom = int(h * (1 - theme.caption_safe_bottom))
    return left, top, right, bottom


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _draw_relationship_frame(
    plan: MotionGraphicPlan,
    theme: DocumentaryVisualTheme,
    progress: float,
) -> Image.Image:
    img = _gradient(theme)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = _safe_box(theme)
    title_font = _font(64)
    node_font = _font(54)
    edge_font = _font(max(34, theme.label_size - 2))

    nodes = list(plan.nodes) or []
    edges = list(plan.relationships) or []
    subject = nodes[-1].upper() if nodes else "OWNERSHIP"
    draw.text(
        (left, top),
        f"{subject} OWNERSHIP",
        fill=theme.text_primary,
        font=title_font,
    )
    draw.text(
        (left, top + 82),
        "VERIFIED RELATIONSHIP • EXPLANATORY",
        fill=theme.text_secondary,
        font=_font(26),
    )

    n = max(len(nodes), 1)
    usable_h = min(620, bottom - top - 470)
    xs = (left + right) // 2
    positions: dict[str, tuple[int, int]] = {}
    for i, node in enumerate(nodes):
        reveal = _ease_out_cubic(max(0.0, (progress - i * 0.22) / 0.42))
        if reveal <= 0:
            continue
        y = top + 330 + int((i / max(n - 1, 1)) * usable_h) if n > 1 else top + 600
        positions[node] = (xs, y)
        x = int(xs + (1 - reveal) * 40)
        card = [left + 32, y - 100, right - 32, y + 100]
        draw.rounded_rectangle(card, radius=18, fill=(22, 27, 41), outline=theme.line, width=4)
        draw.rectangle([card[0], card[1], card[0] + 10, card[3]], fill=theme.accent)
        role = "OWNER" if i == 0 else "OWNED ENTITY"
        draw.text((card[0] + 34, card[1] + 22), role, fill=theme.accent, font=_font(28))
        lines = _wrap(draw, node, node_font, right - left - 120)
        ty = card[1] + 65
        for li, line in enumerate(lines):
            draw.text(
                (card[0] + 34, ty + li * 56),
                line,
                fill=theme.text_primary,
                font=node_font,
            )

    for ei, edge in enumerate(edges):
        reveal = _ease_out_cubic(max(0.0, (progress - 0.42 - ei * 0.1) / 0.48))
        if reveal <= 0:
            continue
        a = positions.get(str(edge.get("from")))
        b = positions.get(str(edge.get("to")))
        if not a or not b:
            continue
        # line grows downward
        y2 = int(a[1] + (b[1] - a[1]) * reveal)
        start_y = a[1] + 100
        end_y = b[1] - 100
        y2 = int(start_y + (end_y - start_y) * reveal)
        draw.line([(a[0], start_y), (a[0], y2)], fill=theme.accent, width=6)
        if reveal > 0.85:
            label = str(edge.get("label") or "")
            mid_y = (start_y + end_y) // 2
            draw.text(
                (a[0] + 28, mid_y - 20),
                label.upper(),
                fill=theme.accent,
                font=edge_font,
            )

    return img


def _draw_timeline_frame(
    plan: MotionGraphicPlan,
    theme: DocumentaryVisualTheme,
    progress: float,
) -> Image.Image:
    img = _gradient(theme)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = _safe_box(theme)
    events = list(plan.events) or []
    draw.text((left, top), "OWNERSHIP HISTORY", fill=theme.text_primary, font=_font(64))
    draw.text(
        (left, top + 82),
        "SOURCE-BOUND DATES • EXPLANATORY",
        fill=theme.text_secondary,
        font=_font(26),
    )
    axis_x = left + 42
    draw.line([(axis_x, top + 220), (axis_x, top + 980)], fill=theme.accent, width=5)
    span = max(len(events), 1)
    for i, ev in enumerate(events):
        reveal = _ease_out_cubic(max(0.0, (progress - i * 0.28) / 0.48))
        if reveal <= 0:
            continue
        y = top + 280 + int(i * (600 / max(span - 1, 1))) if span > 1 else top + 580
        r = 9
        draw.ellipse([axis_x - r, y - r, axis_x + r, y + r], fill=theme.accent)
        card = [axis_x + 34, y - 92, right - 24, y + 130]
        draw.rounded_rectangle(card, radius=18, fill=(22, 27, 41), outline=theme.line, width=4)
        draw.rectangle([card[0], card[1], card[0] + 9, card[3]], fill=theme.accent)
        draw.text((card[0] + 34, y - 66), str(ev.get("date")), fill=theme.accent, font=_font(58))
        label = str(ev.get("label") or "")[:90]
        for li, line in enumerate(_wrap(draw, label, _font(46), right - axis_x - 110)[:2]):
            draw.text(
                (card[0] + 34, y + 18 + li * 48),
                line,
                fill=theme.text_primary,
                font=_font(44),
            )
    return img


def _draw_map_frame(
    plan: MotionGraphicPlan,
    theme: DocumentaryVisualTheme,
    progress: float,
) -> Image.Image:
    img = _gradient(theme)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = _safe_box(theme)
    loc = plan.map_location or (plan.nodes[0] if plan.nodes else "Location")
    draw.text((left, top), "LOCATION", fill=theme.text_secondary, font=_font(theme.label_size))
    # Abstract landmass silhouette — not a fake globe animation
    cx, cy = (left + right) // 2, (top + bottom) // 2
    radius = int(180 + 40 * math.sin(progress * math.pi))
    bbox = [cx - radius, cy - int(radius * 0.7), cx + radius, cy + int(radius * 0.7)]
    draw.ellipse(bbox, outline=theme.line, width=2)
    pulse = int(12 + 8 * _ease_out_cubic(progress))
    draw.ellipse([cx - pulse, cy - pulse, cx + pulse, cy + pulse], fill=theme.accent)
    lines = _wrap(draw, loc, _font(44), right - left)
    for i, line in enumerate(lines[:3]):
        bbox_t = draw.textbbox((0, 0), line, font=_font(44))
        tw = bbox_t[2] - bbox_t[0]
        draw.text((cx - tw // 2, cy + radius * 0.55 + i * 50), line, fill=theme.text_primary, font=_font(44))
    return img


def _draw_evidence_card_frame(
    plan: MotionGraphicPlan,
    theme: DocumentaryVisualTheme,
    progress: float,
) -> Image.Image:
    img = _gradient(theme)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = _safe_box(theme)
    # Explicit editorial framing — never looks like a filing/newspaper
    reveal = _ease_out_cubic(progress)
    draw.text(
        (left, top),
        "DOCUMENTARY NOTES",
        fill=theme.accent,
        font=_font(theme.label_size),
    )
    disclaimer = str((plan.style or {}).get("disclaimer") or "Explanatory graphic — not an official document")
    draw.text((left, top + 48), disclaimer, fill=theme.text_secondary, font=_font(22))
    body = plan.labels[1] if len(plan.labels) > 1 else (plan.labels[0] if plan.labels else "")
    y = top + 140
    for line in _wrap(draw, body, _font(40), right - left)[:8]:
        alpha_shift = int((1 - reveal) * 30)
        draw.text((left, y + alpha_shift), line, fill=theme.text_primary, font=_font(40))
        y += 52
    return img


def _draw_counter_frame(
    plan: MotionGraphicPlan,
    theme: DocumentaryVisualTheme,
    progress: float,
) -> Image.Image:
    img = _gradient(theme)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = _safe_box(theme)
    value = plan.labels[0] if plan.labels else ""
    caption = plan.labels[1] if len(plan.labels) > 1 else ""
    draw.text((left, top), "VERIFIED FIGURE", fill=theme.text_secondary, font=_font(theme.label_size))
    scale = 0.7 + 0.3 * _ease_out_cubic(progress)
    font = _font(int(96 * scale))
    bbox = draw.textbbox((0, 0), value, font=font)
    tw = bbox[2] - bbox[0]
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    draw.text((cx - tw // 2, cy - 60), value, fill=theme.accent, font=font)
    y = cy + 60
    for line in _wrap(draw, caption, _font(32), right - left)[:4]:
        bb = draw.textbbox((0, 0), line, font=_font(32))
        draw.text((cx - (bb[2] - bb[0]) // 2, y), line, fill=theme.text_primary, font=_font(32))
        y += 40
    return img


def render_frame(plan: MotionGraphicPlan, theme: DocumentaryVisualTheme, progress: float) -> Image.Image:
    prim = (plan.primitive or "EvidenceCard").strip()
    if prim == "RelationshipGraph" or prim == "EntityFlow":
        return _draw_relationship_frame(plan, theme, progress)
    if prim == "Timeline":
        return _draw_timeline_frame(plan, theme, progress)
    if prim == "MapHighlight":
        return _draw_map_frame(plan, theme, progress)
    if prim == "Counter":
        return _draw_counter_frame(plan, theme, progress)
    if prim == "DocumentHighlight":
        # Without a real document bitmap we refuse to fake one — use evidence card style with banner
        img = _draw_evidence_card_frame(plan, theme, progress)
        d = ImageDraw.Draw(img)
        d.text((60, 80), "SOURCE DOCUMENT COMPOSITION", fill=theme.accent, font=_font(24))
        return img
    return _draw_evidence_card_frame(plan, theme, progress)


def qa_check_frame(img: Image.Image, theme: DocumentaryVisualTheme) -> dict[str, Any]:
    w, h = img.size
    left, top, right, bottom = _safe_box(theme)
    issues: list[str] = []
    if w != theme.width or h != theme.height:
        issues.append("dimension_mismatch")
    # Sample caption band — should not be pure accent (text dumped in subtitle zone)
    band = img.crop((0, int(h * (1 - theme.caption_safe_bottom)), w, h))
    # crude: ensure band mostly dark background
    sample = band.resize((32, 8))
    pixels = list(sample.getdata())
    bright = sum(1 for p in pixels if (p[0] + p[1] + p[2] if not isinstance(p, int) else p) > 500)
    if bright > len(pixels) * 0.55:
        issues.append("caption_band_busy")
    return {
        "ok": not issues,
        "issues": issues,
        "safe_box": {"left": left, "top": top, "right": right, "bottom": bottom},
        "size": [w, h],
    }


class MotionGraphicRenderer:
    """Render MotionGraphicPlan → H.264 vertical MP4 (isolated clip)."""

    name = "internal_motion_graphics"

    def __init__(self, theme: DocumentaryVisualTheme | None = None) -> None:
        self.theme = theme or DEFAULT_THEME

    def render(
        self,
        plan: MotionGraphicPlan,
        *,
        output_dir: str | Path,
        job_id: str = "",
    ) -> MotionGraphicRenderResult:
        if not plan.primitive:
            return MotionGraphicRenderResult(ok=False, error="missing_primitive", plan_id=plan.plan_id)
        if plan.primitive == "DocumentHighlight" and not plan.document_asset_id:
            return MotionGraphicRenderResult(
                ok=False, error="document_highlight_requires_asset", plan_id=plan.plan_id
            )
        if plan.primitive == "RelationshipGraph":
            for edge in plan.relationships or []:
                if not edge.get("claim_id") or not edge.get("evidence_id"):
                    return MotionGraphicRenderResult(
                        ok=False, error="edge_missing_claim_or_evidence", plan_id=plan.plan_id
                    )

        theme = self.theme
        duration = float(plan.duration or 3.0)
        fps = int(plan.fps or theme.fps)
        frames_n = max(1, int(duration * fps))
        out_root = Path(output_dir)
        if job_id:
            out_root = out_root / "jobs" / job_id / "recovery" / "motion"
        else:
            out_root = out_root / "recovery" / "motion"
        out_root.mkdir(parents=True, exist_ok=True)
        out_path = out_root / f"{plan.plan_id.replace(':', '_')}.mp4"

        tmp = Path(tempfile.mkdtemp(prefix="mg_frames_"))
        try:
            qa = {}
            for i in range(frames_n):
                progress = i / max(frames_n - 1, 1)
                frame = render_frame(plan, theme, progress)
                if i == frames_n // 2:
                    qa = qa_check_frame(frame, theme)
                frame.save(tmp / f"frame_{i:04d}.png")

            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(tmp / "frame_%04d.png"),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(out_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return MotionGraphicRenderResult(
                    ok=False,
                    error=f"ffmpeg_failed:{(result.stderr or '')[-400:]}",
                    plan_id=plan.plan_id,
                )
            if not qa.get("ok", True):
                return MotionGraphicRenderResult(
                    ok=False,
                    error=f"qa_failed:{qa.get('issues')}",
                    plan_id=plan.plan_id,
                    path=str(out_path),
                    qa=qa,
                )

            digest = hashlib.sha256(out_path.read_bytes()).hexdigest()[:24]
            provenance = {
                "provider": "internal_motion_graphics",
                "synthetic": True,
                "evidence_role": "EXPLANATORY",
                "claim_ids": list(plan.claim_ids),
                "evidence_ids": list(plan.evidence_ids),
                "renderer": self.name,
                "template": plan.primitive,
                "template_version": plan.template_version,
                "render_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "content_fingerprint": digest,
                "explanatory_graphic": True,
                "not_documentary_footage": True,
            }
            return MotionGraphicRenderResult(
                ok=True,
                path=str(out_path),
                plan_id=plan.plan_id,
                duration_sec=duration,
                width=theme.width,
                height=theme.height,
                fps=fps,
                content_fingerprint=digest,
                qa=qa,
                provenance=provenance,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
