#!/usr/bin/env python3
"""
transcript-to-epub: Convert raw timestamped transcripts into clean EPUB books.

Supports:
    - Local markdown files with timestamps
    - YouTube URLs (auto-fetches transcript + channel name)

Usage:
    python3 build.py <input.md|youtube-url> [--title TITLE] [--cover PATH] [--cover-method METHOD] [--output DIR] [--css PATH]

Speaker/author is auto-detected:
    - YouTube: channel name from video page
    - Transcripts: speaker names from >> markers
    - Fallback: "Various Speakers"

Requirements:
    - pandoc
    - Python 3 with Pillow (fallback cover generation)
    - youtube-transcript-api (for YouTube URLs): pip install youtube-transcript-api
"""

import re
import sys
import os
import subprocess
import argparse
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YT_API = True
except ImportError:
    HAS_YT_API = False


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    if re.fullmatch(r"[\w-]{11}", url):
        return url

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if "youtube.com" in host:
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("embed", "shorts", "v"):
            return parts[1]

    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0]

    return None


def is_youtube_url(text: str) -> bool:
    """Check if input looks like a YouTube URL or video ID."""
    return extract_video_id(text) is not None


def fetch_youtube_transcript(url: str, language: str = "en") -> tuple[str, str, str]:
    """
    Fetch transcript from YouTube URL.
    Returns (title, channel_name, transcript_text).
    """
    if not HAS_YT_API:
        print("Error: youtube-transcript-api not installed.", file=sys.stderr)
        print("  Install with: pip install youtube-transcript-api", file=sys.stderr)
        sys.exit(1)

    video_id = extract_video_id(url)
    if not video_id:
        print(f"Error: Could not extract video ID from: {url}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching transcript for video: {video_id}")

    ytt_api = YouTubeTranscriptApi()

    try:
        transcript = ytt_api.fetch(video_id, languages=[language])
    except Exception:
        try:
            transcript = ytt_api.fetch(video_id)
        except Exception as e:
            print(f"Error: Could not fetch transcript: {e}", file=sys.stderr)
            sys.exit(1)

    # Fetch metadata (title + channel)
    title, channel = _fetch_video_metadata(video_id)

    # Format transcript as timestamped text
    lines = []
    for entry in transcript.snippets:
        minutes = int(entry.start // 60)
        seconds = int(entry.start % 60)
        hours = minutes // 60
        minutes = minutes % 60
        timestamp = f"**{hours:02d}:{minutes:02d}:{seconds:02d}**"
        lines.append(f"{timestamp}: {entry.text}")

    return title, channel, "\n".join(lines)


def _fetch_video_metadata(video_id: str) -> tuple[str, str]:
    """Fetch video title and channel name. Returns (title, channel)."""
    # Method 1: yt-dlp (most reliable)
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--print", "%(title)s\t%(channel)s",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("\t", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return parts[0], "Unknown Channel"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 2: HTML scrape via requests
    try:
        import requests
        resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        html = resp.text

        # Title
        title = None
        m = re.search(r'<meta\s+name="title"\s+content="([^"]+)"', html)
        if m:
            title = m.group(1).strip()
        else:
            m = re.search(r"<title>(.+?)</title>", html)
            if m:
                title = re.sub(r"\s*[-–]\s*YouTube\s*$", "", m.group(1).strip())

        # Channel name
        channel = None
        m = re.search(r'<link\s+itemprop="name"\s+content="([^"]+)"', html)
        if m:
            channel = m.group(1).strip()
        else:
            m = re.search(r'"ownerChannelName":"([^"]+)"', html)
            if m:
                channel = m.group(1).strip()

        return title or video_id, channel or "Unknown Channel"
    except Exception:
        pass

    return video_id, "Unknown Channel"


# ---------------------------------------------------------------------------
# Speaker detection
# ---------------------------------------------------------------------------

def detect_speakers(content: str) -> str:
    """Extract speaker names from >> markers in transcript. Returns formatted string."""
    speakers = set()

    for line in content.split("\n"):
        stripped = line.strip()
        # Match >> Speaker Name: or >> Speaker Name followed by text
        m = re.match(r"^>>\s*([A-Za-z][A-Za-z .'-]+?):", stripped)
        if m:
            name = m.group(1).strip()
            if len(name) > 2 and len(name) < 60:
                speakers.add(name)
            continue

        # Match **timestamp**: >> Speaker Name:
        m = re.match(r"^\*\*\d+:\d{2}:\d{2}\*\*:\s*>>\s*([A-Za-z][A-Za-z .'-]+?):", stripped)
        if m:
            name = m.group(1).strip()
            if len(name) > 2 and len(name) < 60:
                speakers.add(name)

    if not speakers:
        return "Various Speakers"

    sorted_speakers = sorted(speakers)
    if len(sorted_speakers) == 1:
        return sorted_speakers[0]
    elif len(sorted_speakers) == 2:
        return f"{sorted_speakers[0]} & {sorted_speakers[1]}"
    else:
        return f"{sorted_speakers[0]}, {sorted_speakers[1]} & {len(sorted_speakers) - 2} more"


# ---------------------------------------------------------------------------
# Transcript cleaning
# ---------------------------------------------------------------------------

def clean_transcript(content: str) -> str:
    """Strip timestamps and speaker markers, then merge lines into paragraphs.

    Recognizes three line shapes, in priority order:
      - ``**HH:MM:SS**: text`` — timestamped line (timestamp removed)
      - ``>> Speaker: text``   — speaker turn (``>>`` removed, starts a new turn)
      - plain prose            — kept as a continuation of the current turn

    Plain prose is retained so an untimestamped transcript still produces a
    book instead of an empty file.
    """
    segments = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("# "):
            continue
        # Drop a previously-injected metadata header so re-running on an
        # already-built transcript.md doesn't duplicate the speakers line.
        if stripped.startswith("**Speakers:**"):
            continue

        m = re.match(r"^\*\*\d+:\d{2}:\d{2}\*\*:\s*(.*)", stripped)
        if m:
            stripped = m.group(1).strip()
            if not stripped:
                continue

        if stripped.startswith(">>"):
            segments.append((stripped.lstrip(">").strip(), True))
        else:
            segments.append((stripped, False))

    turns: list[list[str]] = []
    current_turn: list[str] = []
    for text, is_speaker in segments:
        if is_speaker and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(text)
    if current_turn:
        turns.append(current_turn)

    paragraphs = []
    for turn in turns:
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(turn))
        current_para: list[str] = []
        char_count = 0
        for sent in sentences:
            current_para.append(sent)
            char_count += len(sent)
            if char_count >= 500 and len(current_para) >= 2:
                paragraphs.append(" ".join(current_para))
                current_para = []
                char_count = 0
        if current_para:
            paragraphs.append(" ".join(current_para))

    return "\n\n".join(paragraphs) + "\n"


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

def extract_title(content: str, filepath: str) -> str:
    """Extract title from markdown h1 or derive from filename."""
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return Path(filepath).stem.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Cover generation
# ---------------------------------------------------------------------------

def generate_cover(title: str, speakers: str, output_path: str, method: str = "auto") -> bool:
    """Render a cover with Pillow. ``method="none"`` skips it."""
    if method == "none":
        return False
    return _cover_pillow(title, speakers, output_path)


def _load_cover_font(size: int):
    """Load a bold system font at ``size``, falling back to Pillow's default."""
    for fp in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """Greedily wrap ``text`` so each line fits within ``max_width`` pixels."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _cover_pillow(title: str, speakers: str, output_path: str) -> bool:
    """Render a cover: wrapped white title, lime accent rule, grey byline."""
    if not HAS_PILLOW:
        print("Warning: Pillow not installed; skipping cover.", file=sys.stderr)
        return False

    width, height, margin = 1600, 2400, 200
    img = Image.new("RGB", (width, height), color="#0C1211")
    draw = ImageDraw.Draw(img)

    title_font = _load_cover_font(110)
    byline_font = _load_cover_font(46)

    y = 360
    for line in _wrap_text(draw, title, title_font, width - 2 * margin):
        line_width = draw.textlength(line, font=title_font)
        draw.text(((width - line_width) / 2, y), line, fill="#FFFFFF", font=title_font)
        y += 140

    draw.rectangle([margin, y + 30, width - margin, y + 38], fill="#B7FF6E")

    byline_width = draw.textlength(speakers, font=byline_font)
    draw.text(((width - byline_width) / 2, height - 260), speakers, fill="#8A8F8C", font=byline_font)

    img.save(output_path, "PNG")
    return True


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def build_css() -> str:
    """Return default EPUB CSS — warm reading page, justified prose,
    print-style paragraph indents, and italic lime-keylined blockquotes
    for interviewer questions (FORSVN brand tokens)."""
    return """@charset "UTF-8";
/* ===== transcript-to-epub default stylesheet ===== */

/* Body: warm off-white, comfortable reading measure */
body {
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, serif;
  font-size: 1em;
  line-height: 1.65;
  color: #1a1a1a;
  background-color: #faf8f3;
  margin: 0 5%;
  text-align: justify;
  -webkit-hyphens: auto;
  -epub-hyphens: auto;
  hyphens: auto;
  orphans: 2;
  widows: 2;
}

/* Paragraphs: indented continuation style, like print books */
p {
  margin: 0;
  text-indent: 1.4em;
  hyphens: auto;
}

/* First paragraph after a heading or break: no indent */
h1 + p, h2 + p, h3 + p,
.no-indent,
p.first,
hr + p {
  text-indent: 0;
}

/* Headings */
h1, h2, h3 {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-weight: 700;
  line-height: 1.2;
  color: #0C1211;
  text-indent: 0;
  text-align: left;
}

h1 {
  font-size: 1.9em;
  margin: 1.2em 0 0.8em;
}

h2 {
  font-size: 1.4em;
  margin: 1.6em 0 0.6em;
  padding-bottom: 0.2em;
  border-bottom: 2px solid #B7FF6E;
}

h3 {
  font-size: 1.15em;
  margin: 1.4em 0 0.4em;
  color: #004700;
}

/* ===== Speaker / interviewer treatment ===== */
/* Interviewer questions: italic, inset, lime keyline */
blockquote {
  margin: 1.4em 0;
  padding: 0.2em 0 0.2em 1.1em;
  border-left: 3px solid #B7FF6E;
  font-style: italic;
  color: #2a2a2a;
  text-indent: 0;
}

blockquote p {
  text-indent: 0;
  margin: 0 0 0.6em 0;
}

blockquote p:last-child {
  margin-bottom: 0;
}

/* The "Speakers:" line under the title */
p strong:first-child {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}

/* Horizontal rule as section divider */
hr {
  border: none;
  border-top: 1px solid #d8d4c8;
  width: 30%;
  margin: 2em auto;
}

/* Cover */
.cover-wrap { text-align: center; margin: 0; padding: 0; }
.cover-wrap img { max-width: 100%; height: auto; }
"""


# ---------------------------------------------------------------------------
# EPUB builder
# ---------------------------------------------------------------------------

def build_epub(
    md_path: str,
    output_path: str,
    title: str,
    speakers: str,
    cover_path: str | None = None,
    css_path: str | None = None,
) -> str:
    """Run pandoc to build the EPUB. Returns the output path."""
    cmd = [
        "pandoc",
        md_path,
        "-o", output_path,
        "--metadata", f"title={title}",
        "--metadata", f"author={speakers}",
        "--metadata", "lang=en",
        "--toc",
        "--toc-depth=1",
        "--split-level=2",
    ]

    if cover_path:
        cmd.extend(["--epub-cover-image", cover_path])

    tmp_css = None
    if css_path:
        cmd.extend(["--css", css_path])
    else:
        fd, tmp_css = tempfile.mkstemp(prefix="t2e-", suffix=".css")
        with os.fdopen(fd, "w") as f:
            f.write(build_css())
        cmd.extend(["--css", tmp_css])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if tmp_css and os.path.exists(tmp_css):
            os.unlink(tmp_css)

    if result.returncode != 0:
        print(f"Error: pandoc failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert transcript markdown or YouTube URL to EPUB"
    )
    parser.add_argument(
        "input",
        help="Input markdown file or YouTube URL/video ID",
    )
    parser.add_argument("--title", default=None, help="Book title (default: from filename or video)")
    parser.add_argument("--speakers", default=None,
                        help="Override speaker/author byline (default: auto-detected from >> markers)")
    parser.add_argument("--cover", default=None, help="Path to custom cover image")
    parser.add_argument("--cover-method", default="auto", choices=["auto", "pillow", "none"],
                        help="Cover generation: auto/pillow (Pillow) or none (default: auto)")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--css", default=None, help="Custom CSS file")
    parser.add_argument("--language", default="en", help="Language code for YouTube transcript (default: en)")
    return parser.parse_args()


def main():
    args = parse_args()

    # An existing file always wins, so an 11-char filename is never mistaken
    # for a YouTube video ID.
    input_path = Path(args.input)
    if input_path.is_file():
        input_path = input_path.resolve()
        content = input_path.read_text(encoding="utf-8")
        title = args.title or extract_title(content, str(input_path))
        speakers = args.speakers or detect_speakers(content)
        default_output_dir = input_path.parent
    elif is_youtube_url(args.input):
        title, channel, raw_transcript = fetch_youtube_transcript(args.input, language=args.language)
        title = args.title or title
        speakers = args.speakers or channel
        content = f"# {title}\n\n{raw_transcript}"
        slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-").lower()[:60]
        default_output_dir = Path.cwd() / (slug or "transcript")
    else:
        print(f"Error: {args.input!r} is not an existing file or a recognizable YouTube URL.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Title:    {title}")
    print(f"Speakers: {speakers}")

    output_dir = Path(args.output).resolve() if args.output else default_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean transcript
    print("Cleaning transcript...")
    cleaned = clean_transcript(content)

    # Write cleaned markdown
    md_output = output_dir / "transcript.md"
    header = f"# {title}\n\n**Speakers:** {speakers}\n\n"
    md_output.write_text(header + cleaned, encoding="utf-8")
    print(f"Wrote:    {md_output}")

    # Generate or copy cover
    cover_path = args.cover
    if not cover_path:
        auto_cover = output_dir / "cover.png"
        if generate_cover(title, speakers, str(auto_cover), method=args.cover_method):
            cover_path = str(auto_cover)
            print(f"Wrote:    {cover_path}")

    # Build EPUB
    epub_output = output_dir / "book.epub"
    print("Building EPUB...")
    build_epub(
        md_path=str(md_output),
        output_path=str(epub_output),
        title=title,
        speakers=speakers,
        cover_path=cover_path,
        css_path=args.css,
    )
    print(f"Wrote:    {epub_output}")

    print("Done.")


if __name__ == "__main__":
    main()
