"""
Render a simple visual electronic signature image for embedding in DOCX.

Uses Pillow. Prefers an italic/oblique system font for a handwritten-style look;
falls back gracefully if no TTF is found.
"""

from __future__ import annotations

import io
import os
from typing import List

from PIL import Image, ImageDraw, ImageFont


def _font_paths() -> List[str]:
    paths: List[str] = []
    if os.name == "nt":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        paths.extend(
            [
                os.path.join(windir, "Fonts", "segoeuii.ttf"),
                os.path.join(windir, "Fonts", "calibrii.ttf"),
                os.path.join(windir, "Fonts", "ariali.ttf"),
            ]
        )
    paths.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    return paths


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_paths():
        if not os.path.isfile(path):
            continue
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_signature_png_bytes(
    signer_text: str,
    *,
    max_width: int = 520,
    pad: int = 16,
) -> bytes:
    """
    Draw a white-background PNG with signer_text as the visual signature line.

    signer_text: usually signer email or full name.
    """
    text = (signer_text or "").strip() or "Signer"
    font = _load_font(36)

    probe = Image.new("RGB", (10, 10), (255, 255, 255))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    w = min(max_width, tw + pad * 2)
    h = th + pad * 2 + 14

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    x, y = pad, pad
    fill = (18, 32, 68)
    draw.text((x, y), text, font=font, fill=fill)

    line_y = y + th + 4
    draw.line([(x, line_y), (x + tw, line_y)], fill=(40, 40, 40), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
