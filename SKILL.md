---
name: transcript-to-epub
description: "Converts YouTube videos or raw timestamped transcripts into clean, formatted EPUB books. Auto-detects speakers/channel name, cleans timestamps, formats paragraphs, generates cover, and builds EPUB."
argument-hint: "<youtube-url|input.md> [--title <title>] [--cover <path>] [--cover-method <method>]"
allowed-tools: Read, Write, Bash, Glob
metadata:
  version: "1.3.0"
---

# Transcript to EPUB

Converts YouTube videos or raw transcripts into clean, readable EPUB books.

## When To Use

- YouTube video URL → auto-fetch transcript + channel name → EPUB
- Raw transcript with `**HH:MM:SS**:` timestamps → clean EPUB
- Podcast transcripts with speaker markers (`>>`) → auto-detect speakers
- Interview transcripts that need formatting into a book

## When NOT To Use

- Already-formatted markdown → just use `pandoc` directly
- Video/audio files without captions → needs captions or manual transcript
- Private/restricted YouTube videos → transcript won't be accessible

## Usage

```bash
# From YouTube URL (auto-detects channel name)
python3 scripts/build.py \
  "https://www.youtube.com/watch?v=VIDEO_ID"

# From YouTube URL with custom title
python3 scripts/build.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --title "My Custom Book Title"

# From local markdown file (auto-detects >> speakers)
python3 scripts/build.py \
  transcript.md --title "Interview Transcript"

# With custom cover image
python3 scripts/build.py \
  transcript.md --cover ./my-cover.png
```

Or via the agent: "Turn this YouTube video into an EPUB book"

## What It Does

### YouTube Input
1. **Extracts** video ID from URL (supports all YouTube URL formats)
2. **Fetches** transcript via `youtube-transcript-api` (no API key needed)
3. **Fetches** video title + channel name from YouTube page
4. Falls through to the standard pipeline below

### Local File Input
1. **Detects** speaker names from `>>` markers (e.g., `>> John:` → "John")
2. Falls through to the standard pipeline below

### Standard Pipeline
1. **Cleans** — removes `**HH:MM:SS**:` timestamp prefixes
2. **Merges** — joins broken mid-sentence lines into flowing paragraphs
3. **Formats** — detects speaker changes (`>>`) and creates proper paragraph breaks
4. **Covers** — generates a cover image (auto-detects best method, or use custom)
5. **Packages** — builds a valid EPUB3 with metadata, TOC, and stylesheet

## Speaker/Author Detection

The skill auto-detects who's speaking:

| Input Type | Detection Method |
|------------|------------------|
| YouTube URL | Channel name from video metadata |
| `>> Speaker Name:` markers | Extracts names from transcript |
| No speakers found | Falls back to "Various Speakers" |

No `--author` flag needed — it's automatic.

## Output Structure

```
<output-dir>/
├── transcript.md      # Cleaned markdown with speaker header
├── book.epub          # Final EPUB
└── cover.png          # Generated cover (if available)
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--title` | Derived from filename/video | Book title (customizable) |
| `--cover` | Auto-generated | Path to custom cover image (PNG/JPG) |
| `--cover-method` | `auto` | Cover method: `auto`, `pillow`, `none` |
| `--output` | Same as input dir | Output directory |
| `--css` | Built-in | Custom CSS for EPUB styling |
| `--language` | `"en"` | Language code for YouTube transcript |

## Cover Generation Methods

| Method | Tool | Notes |
|--------|------|-------|
| `auto` / `pillow` | Python Pillow | Default. No external deps, always available |
| `none` | — | Skip cover generation |
| `--cover PATH` | Any image | Use your own image (best quality) |

## Supported YouTube URL Formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- Plain video ID: `dQw4w9WgXcQ`

## Prerequisites

- `pandoc` (`brew install pandoc`) — builds the EPUB
- Python 3.10+ with Pillow (`pip3 install Pillow`) — cover generation
- `youtube-transcript-api` (`pip3 install youtube-transcript-api`) — only for YouTube URLs
- `yt-dlp` (optional, `brew install yt-dlp`) — more reliable YouTube title/channel; falls back to HTML scrape
