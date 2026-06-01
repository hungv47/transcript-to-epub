"""Engine adapter for the web app.

Reuses the pure functions from the existing CLI engine (``scripts/build.py``)
and adds the things the web product needs that the CLI doesn't:

  - freemium variants (free preview vs. paid unlock)
  - "Made with TalkToBook" watermark colophon on the free preview
  - owned-content front matter (the CLI's "unofficial reading edition"
    disclaimer is for ripping *other* people's videos; this product targets a
    creator's *own* content, attested by an ownership checkbox)
  - .srt / .vtt subtitle normalization
  - custom accent colour and cover for the paid edition
  - extra paid formats: PDF (WeasyPrint) and Kindle AZW3 (Calibre)

Format generation is capability-detected and best-effort: EPUB is always
produced; PDF/AZW3 are produced only where their tool is on PATH. This keeps
the service runnable in environments missing WeasyPrint/Calibre (prod installs
both — see Dockerfile).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

# Import the existing CLI engine as a library for its pure helpers.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import build as t2e  # noqa: E402  (clean_transcript, detect_speakers, etc.)

BRAND_ACCENT = "#7F1D1D"
BRAND_INK = "#0C1211"
# Credit is never silently dropped: when no creator can be detected, the byline
# degrades to this rather than vanishing. The author is never user-editable —
# this product credits the original creators of the content.
UNKNOWN_CREATORS = t2e.UNKNOWN_CREATORS

try:
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YOUTUBE_TRANSCRIPT = True
except ImportError:
    YouTubeTranscriptApi = None
    HAS_YOUTUBE_TRANSCRIPT = False


class EngineError(RuntimeError):
    """Raised when a conversion step fails (pandoc/weasyprint/calibre)."""


class TranscriptFetchError(RuntimeError):
    """Raised when a URL transcript cannot be fetched for user-correctable reasons."""


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------

def capabilities() -> dict:
    """Which output formats this host can actually produce, right now."""
    return {
        "epub": bool(shutil.which("pandoc")),
        "pdf": bool(shutil.which("pandoc") and shutil.which("weasyprint")),
        "azw3": bool(shutil.which("ebook-convert")),
        "cover": HAS_PILLOW,
        "youtube": HAS_YOUTUBE_TRANSCRIPT,
    }


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def is_youtube_source(url: str) -> bool:
    """True when the source string is a YouTube URL or video id."""
    return t2e.extract_video_id((url or "").strip()) is not None


def fetch_youtube_source(url: str, language: str = "en") -> dict:
    """Fetch a YouTube transcript and lightweight metadata for web preview builds."""
    source = (url or "").strip()
    video_id = t2e.extract_video_id(source)
    if not video_id:
        raise TranscriptFetchError("Only YouTube URLs are supported right now.")
    if not HAS_YOUTUBE_TRANSCRIPT or YouTubeTranscriptApi is None:
        raise TranscriptFetchError("YouTube transcript fetching is not installed on this server.")

    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video_id, languages=[language])
    except Exception as e:
        if e.__class__.__name__ == "NoTranscriptFound":
            try:
                transcript = api.fetch(video_id)
            except Exception as fallback:
                raise _youtube_fetch_error(fallback) from fallback
        else:
            raise _youtube_fetch_error(e) from e

    raw_text = _format_youtube_transcript(transcript)
    if not raw_text.strip():
        raise TranscriptFetchError("This video returned an empty transcript.")

    canonical = t2e.canonical_youtube_url(video_id)
    title, author = _fetch_youtube_metadata(canonical, video_id)
    return {
        "title": title,
        "author": author,
        "source_url": canonical,
        "raw_text": raw_text,
    }


def _format_youtube_transcript(transcript) -> str:
    lines: list[str] = []
    for entry in transcript:
        if isinstance(entry, dict):
            start = float(entry.get("start") or 0)
            text = str(entry.get("text") or "").strip()
        else:
            start = float(getattr(entry, "start", 0) or 0)
            text = str(getattr(entry, "text", "") or "").strip()
        if not text:
            continue
        minutes = int(start // 60)
        seconds = int(start % 60)
        hours = minutes // 60
        minutes %= 60
        lines.append(f"**{hours:02d}:{minutes:02d}:{seconds:02d}**: {text}")
    return "\n".join(lines)


def _fetch_youtube_metadata(canonical_url: str, video_id: str) -> tuple[str, str | None]:
    """Use YouTube oEmbed for title/channel without requiring a Data API key."""
    try:
        import requests

        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": canonical_url, "format": "json"},
            headers={"User-Agent": "TalkToBook/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        title = (data.get("title") or "").strip() or video_id
        author = (data.get("author_name") or "").strip() or None
        return title, author
    except Exception:
        pass

    try:
        from urllib.request import Request, urlopen

        qs = urlencode({"url": canonical_url, "format": "json"})
        req = Request(
            f"https://www.youtube.com/oembed?{qs}",
            headers={"User-Agent": "TalkToBook/1.0"},
        )
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        title = (data.get("title") or "").strip() or video_id
        author = (data.get("author_name") or "").strip() or None
        return title, author
    except Exception:
        return video_id, None


def _youtube_fetch_error(error: Exception) -> TranscriptFetchError:
    kind = error.__class__.__name__
    if kind == "VideoUnavailable":
        return TranscriptFetchError("That YouTube video is unavailable.")
    if kind == "TranscriptsDisabled":
        return TranscriptFetchError("That video has transcripts disabled. Upload a transcript file instead.")
    if kind == "NoTranscriptFound":
        return TranscriptFetchError("No transcript was found for that video. Upload captions or a transcript file instead.")
    if kind == "RequestBlocked":
        return TranscriptFetchError("YouTube blocked transcript access from this server. Upload a transcript file instead.")
    return TranscriptFetchError("Could not fetch a transcript for that YouTube URL.")

_VTT_TS = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->")
_CUE_NUM = re.compile(r"^\d+$")


def normalize_input(text: str, fmt: str) -> str:
    """Return transcript text the cleaner can consume.

    ``.srt``/``.vtt`` carry cue numbers and ``-->`` timecode lines that aren't
    prose; strip them (and collapse the consecutive duplicate caption lines that
    auto-captioning emits) before handing off to the paragraph cleaner.
    """
    fmt = (fmt or "").lower().lstrip(".")
    if fmt not in ("srt", "vtt"):
        return text

    out: list[str] = []
    last = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if _VTT_TS.search(line) or "-->" in line:
            continue
        if _CUE_NUM.fullmatch(line):
            continue
        # Drop inline cue tags like <00:00:01.000> and <c> styling.
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line == last:
            continue
        out.append(line)
        last = line
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Book assembly (owned-content framing)
# ---------------------------------------------------------------------------

WATERMARK = (
    "\n\n----\n\n"
    "*Made with **TalkToBook** — turn your podcast, talk, or interview into a "
    "Kindle-ready book.*\n"
)


def assemble_book(
    title: str,
    author: str | None,
    source_url: str | None,
    body: str,
    *,
    watermark: bool,
) -> str:
    """Compose the Markdown book: title + byline front matter, then body.

    Owned-content framing — the user attests ownership, so there is no
    "unofficial edition / no-copyright-claim" disclaimer (that's the CLI's job
    for third-party rips). The free preview gets a removable watermark colophon.
    """
    lines = [f"# {title}", ""]
    if author:
        lines.append(f"*by {author}*")
        lines.append("")
    if source_url:
        lines.append(f"Adapted from the original recording: {source_url}")
        lines.append("")
    md = "\n".join(lines) + "\n" + body.strip() + "\n"
    if watermark:
        md += WATERMARK
    return md


# ---------------------------------------------------------------------------
# Stylesheet & cover
# ---------------------------------------------------------------------------

def css_for(accent: str = BRAND_ACCENT) -> str:
    """The engine's reading stylesheet, re-tinted to a custom accent."""
    css = t2e.build_css()
    accent = (accent or BRAND_ACCENT).strip()
    if accent and accent.upper() != BRAND_ACCENT:
        css = css.replace(BRAND_ACCENT, accent)
    return css


def _load_font(size: int):
    for fp in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_cover(
    title: str,
    author: str | None,
    out_path: Path,
    *,
    accent: str = BRAND_ACCENT,
    bg: str = BRAND_INK,
) -> bool:
    """Render a calm plain cover (dark ink, single accent rule, white title).

    Parameterized version of the CLI's Pillow cover so the paid edition can use
    the creator's accent. Returns False (no cover) if Pillow is unavailable.
    """
    if not HAS_PILLOW:
        return False
    width, height, margin = 1600, 2400, 200
    img = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(img)
    title_font = _load_font(110)
    byline_font = _load_font(46)

    y = 360
    for line in t2e._wrap_text(draw, title, title_font, width - 2 * margin):
        line_w = draw.textlength(line, font=title_font)
        draw.text(((width - line_w) / 2, y), line, fill="#FFFFFF", font=title_font)
        y += 140

    draw.rectangle([margin, y + 30, width - margin, y + 38], fill=accent)

    if author:
        bw = draw.textlength(author, font=byline_font)
        draw.text(((width - bw) / 2, height - 260), author, fill="#8A8F8C", font=byline_font)

    img.save(str(out_path), "PNG")
    return True


def cover_prompt(title: str, author: str | None) -> str:
    """AI image-gen prompt for a paid custom cover (delegates to the engine)."""
    return t2e.cover_prompt(title, author or "")


# ---------------------------------------------------------------------------
# Format builders
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise EngineError(f"{cmd[0]} not installed") from e
    if r.returncode != 0:
        raise EngineError(f"{cmd[0]} failed: {(r.stderr or r.stdout).strip()[:600]}")


def build_epub(md_path: Path, out_path: Path, css_path: Path, title: str,
               author: str | None, cover_path: Path | None) -> None:
    cmd = [
        "pandoc", str(md_path), "-o", str(out_path),
        "--metadata", f"title={title}",
        "--metadata", f"author={author or ''}",
        "--metadata", "lang=en",
        "--epub-title-page=false",
        "--toc", "--toc-depth=1", "--split-level=2",
        "--css", str(css_path),
    ]
    if cover_path:
        cmd += ["--epub-cover-image", str(cover_path)]
    _run(cmd)


def build_pdf(md_path: Path, out_path: Path, css_path: Path, title: str,
              author: str | None) -> None:
    _run([
        "pandoc", str(md_path), "-o", str(out_path),
        "--pdf-engine=weasyprint",
        "--metadata", f"title={title}",
        "--metadata", f"author={author or ''}",
        "--css", str(css_path),
    ])


def build_azw3(epub_path: Path, out_path: Path) -> None:
    # Calibre converts the finished EPUB to Kindle AZW3 (modern Kindle format).
    _run(["ebook-convert", str(epub_path), str(out_path)])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def derive_metadata(raw_text: str, fmt: str, title: str | None,
                    author: str | None) -> tuple[str, str | None]:
    """Fill in a missing title/author from the transcript itself."""
    text = normalize_input(raw_text, fmt)
    title = (title or "").strip() or t2e.extract_title(text, "your-book")
    if not (author or "").strip():
        detected = t2e.detect_speakers(text)
        author = None if detected == "Various Speakers" else detected
    return title, ((author or "").strip() or None)


def generate(
    job_dir: Path,
    *,
    raw_text: str,
    fmt: str,
    title: str,
    author: str | None,
    source_url: str | None,
    paid: bool,
    accent: str = BRAND_ACCENT,
    cover_image: Path | None = None,
) -> dict:
    """Build the book for a job. Returns a dict of produced files + metadata.

    Free preview: watermark colophon, plain brand-accent cover, EPUB only.
    Paid unlock: no watermark, custom accent, custom cover (or plain), and PDF +
    Kindle AZW3 where the host can produce them.
    """
    job_dir.mkdir(parents=True, exist_ok=True)
    text = normalize_input(raw_text, fmt)
    if not text.strip():
        raise EngineError("Transcript is empty after cleaning.")

    body = t2e.clean_transcript(text)
    if not body.strip():
        raise EngineError("No readable text found in the transcript.")

    accent = accent if paid else BRAND_ACCENT
    md = assemble_book(title, author, source_url, body, watermark=not paid)
    md_path = job_dir / "book.md"
    md_path.write_text(md, encoding="utf-8")

    css_path = job_dir / "style.css"
    css_path.write_text(css_for(accent), encoding="utf-8")

    # Cover: paid + uploaded image wins; else a plain rendered cover.
    cover_path: Path | None = None
    if paid and cover_image and Path(cover_image).exists():
        cover_path = Path(cover_image)
    else:
        cp = job_dir / "cover.png"
        if render_cover(title, author, cp, accent=accent):
            cover_path = cp

    outputs: dict[str, str] = {}
    epub_path = job_dir / "book.epub"
    try:
        build_epub(md_path, epub_path, css_path, title, author, cover_path)
    except EngineError:
        # A bad/unreadable custom cover shouldn't fail the whole build — retry
        # without it rather than 500 a paying customer. Re-raise if it wasn't
        # the cover (no cover supplied).
        if cover_path is not None:
            build_epub(md_path, epub_path, css_path, title, author, None)
        else:
            raise
    outputs["epub"] = epub_path.name

    if paid:
        caps = capabilities()
        if caps["pdf"]:
            try:
                pdf_path = job_dir / "book.pdf"
                build_pdf(md_path, pdf_path, css_path, title, author)
                outputs["pdf"] = pdf_path.name
            except EngineError:
                pass
        if caps["azw3"]:
            try:
                azw3_path = job_dir / "book.azw3"
                build_azw3(epub_path, azw3_path)
                outputs["azw3"] = azw3_path.name
            except EngineError:
                pass

    return {
        "title": title,
        "author": author,
        "outputs": outputs,
        "cover_prompt": cover_prompt(title, author),
        "word_count": len(body.split()),
    }
