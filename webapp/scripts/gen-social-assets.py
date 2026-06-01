"""Generate the OG image (1200x630) and Apple touch icon from the brand palette.

Run: .venv/bin/python scripts/gen-social-assets.py
Outputs: static/og.png, static/apple-touch-icon.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "static"
OUT.mkdir(parents=True, exist_ok=True)

INK = (12, 18, 17)
LIME = (183, 255, 110)
PAPER = (250, 248, 243)
MUTED_INK = (154, 166, 161)


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
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img)

    # Subtle radial wash so the panel doesn't read flat.
    wash = Image.new("RGB", (W, H), INK)
    wdraw = ImageDraw.Draw(wash)
    for r in range(720, 0, -8):
        alpha = int(40 * (1 - r / 720))
        col = tuple(min(255, INK[i] + alpha) for i in range(3))
        wdraw.ellipse((W - 200 - r, -200 - r, W + 100 + r, 300 + r), fill=col)
    wash = wash.filter(ImageFilter.GaussianBlur(80))
    img = ImageChops_blend(img, wash)

    draw = ImageDraw.Draw(img)

    # Lime rule
    draw.rectangle((80, 96, 200, 102), fill=LIME)

    # Wordmark
    f_word = _font(38, "bold")
    f_title = _font(96, "bold")
    f_sub = _font(34, "regular")
    f_meta = _font(22, "regular")

    draw.text((80, 130), "TalkToBook", font=f_word, fill=PAPER, anchor="lt")
    draw.text((80, 230), "Turn a podcast into a book", font=f_title, fill=PAPER, anchor="lt")
    sub1 = "your readers actually finish."
    draw.text((80, 350), sub1, font=f_title, fill=LIME, anchor="lt")
    sub2 = "Paste a transcript, get a designed EPUB."
    draw.text((80, 480), sub2, font=f_sub, fill=MUTED_INK, anchor="lt")
    draw.text((80, 525), "Free preview. $9 to unlock. talktobook.com", font=f_meta, fill=MUTED_INK, anchor="lt")

    img.save(OUT / "og.png", "PNG", optimize=True)


def ImageChops_blend(a: Image.Image, b: Image.Image) -> Image.Image:
    from PIL import ImageChops
    return ImageChops.screen(a, b)


def build_apple() -> None:
    """180x180 apple touch icon — solid ink with lime mark."""
    S = 180
    img = Image.new("RGB", (S, S), INK)
    draw = ImageDraw.Draw(img)
    f = _font(120, "bold")
    draw.text((S / 2, S / 2 - 10), "TB", font=f, fill=LIME, anchor="mm")
    draw.rectangle((S / 2 - 36, S - 48, S / 2 + 36, S - 42), fill=LIME)
    img.save(OUT / "apple-touch-icon.png", "PNG", optimize=True)


if __name__ == "__main__":
    build_og()
    build_apple()
    print(f"Wrote {OUT/'og.png'} and {OUT/'apple-touch-icon.png'}")
