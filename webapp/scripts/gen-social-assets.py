"""Generate the OG image (1200x630) and Apple touch icon from the brand palette.

Run: .venv/bin/python scripts/gen-social-assets.py
Outputs: static/og.png, static/apple-touch-icon.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "static"
OUT.mkdir(parents=True, exist_ok=True)

INK = (30, 26, 23)
PAPER = (247, 240, 229)
PANEL = (255, 250, 242)
MUTED = (111, 101, 94)
RULE = (217, 205, 189)
ACCENT = (127, 29, 29)


def _font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """Find a usable system grotesque. Falls back to PIL's default."""
    candidates = {
        "regular": [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
        "bold": [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
    }
    for p in candidates[weight]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, s: str, font) -> int:
    bbox = draw.textbbox((0, 0), s, font=font)
    return bbox[2] - bbox[0]


def build_og() -> None:
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)

    draw.rectangle((64, 58, W - 64, H - 58), outline=RULE, width=2)
    draw.rectangle((80, 92, 204, 98), fill=ACCENT)
    draw.rectangle((760, 112, 1088, 514), fill=PANEL, outline=RULE, width=2)
    draw.rectangle((792, 150, 928, 156), fill=ACCENT)
    draw.line((792, 236, 1052, 236), fill=RULE, width=2)
    draw.line((792, 282, 1052, 282), fill=RULE, width=2)
    draw.line((792, 328, 1052, 328), fill=RULE, width=2)
    draw.line((792, 374, 1008, 374), fill=RULE, width=2)

    f_word = _font(38, "bold")
    f_title = _font(82, "bold")
    f_sub = _font(34, "regular")
    f_meta = _font(22, "regular")
    f_card = _font(30, "bold")

    draw.text((80, 126), "TalkToBook", font=f_word, fill=INK, anchor="lt")
    draw.text((80, 206), "Turn a URL into", font=f_title, fill=INK, anchor="lt")
    draw.text((80, 304), "a lead magnet", font=f_title, fill=ACCENT, anchor="lt")
    draw.text((80, 402), "EPUB.", font=f_title, fill=ACCENT, anchor="lt")
    draw.text((80, 502), "For talks, webinars, and lessons you own.", font=f_sub, fill=MUTED, anchor="lt")
    draw.text((80, 550), "Free preview. $7 clean edition. talktobook.com", font=f_meta, fill=MUTED, anchor="lt")
    draw.text((792, 184), "Lead magnet", font=f_card, fill=INK, anchor="lt")
    draw.text((792, 422), "Course companion", font=f_card, fill=INK, anchor="lt")

    img.save(OUT / "og.png", "PNG", optimize=True)


def build_apple() -> None:
    """180x180 apple touch icon from the editorial identity."""
    S = 180
    img = Image.new("RGB", (S, S), PAPER)
    draw = ImageDraw.Draw(img)
    f = _font(120, "bold")
    draw.rounded_rectangle((10, 10, S - 10, S - 10), radius=28, outline=RULE, width=4)
    draw.text((S / 2, S / 2 - 8), "TB", font=f, fill=INK, anchor="mm")
    draw.rectangle((S / 2 - 42, S - 48, S / 2 + 42, S - 42), fill=ACCENT)
    img.save(OUT / "apple-touch-icon.png", "PNG", optimize=True)


if __name__ == "__main__":
    build_og()
    build_apple()
    print(f"Wrote {OUT/'og.png'} and {OUT/'apple-touch-icon.png'}")
