# transcript-to-epub

Turn a YouTube video or a raw timestamped transcript into a clean, readable **EPUB** book — speakers detected, timestamps stripped, paragraphs reflowed, cover generated.

<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/809a265e-e607-413f-a903-4516c9c5f1e4" />
<img width="1108" height="830" alt="image" src="https://github.com/user-attachments/assets/b4a14df1-a82f-4053-9fe3-deba4d1f6923" />

Works as a standalone Python script or as a [Claude Code](https://docs.claude.com/en/docs/claude-code) skill (`SKILL.md` included).

## What it does

- **YouTube URL** → fetches the transcript (no API key), pulls the title + channel name, builds an EPUB.
- **Local transcript** → detects `>> Speaker:` markers, strips `**HH:MM:SS**:` timestamps, merges broken lines into flowing paragraphs.
- **Cover** → generates a branded cover image (wrapped title + byline) with Pillow, or use your own with `--cover`.
- **Package** → builds a valid EPUB3 with metadata and stylesheet via `pandoc`.

## Install

```bash
# clone, then install the prerequisites
brew install pandoc
pip3 install Pillow youtube-transcript-api
# yt-dlp is optional but gives more reliable YouTube title/channel:
brew install yt-dlp
```

To use it as a Claude Code skill, copy this folder into your skills directory
(e.g. `~/.claude/skills/transcript-to-epub/`).

## Usage

```bash
# From a YouTube URL (auto-detects title + channel)
python3 scripts/build.py "https://www.youtube.com/watch?v=VIDEO_ID"

# From a local transcript, with a custom title
python3 scripts/build.py transcript.md --title "My Interview Book"

# Bring your own cover
python3 scripts/build.py transcript.md --cover ./cover.png
```

Output (a `book.epub`, the cleaned `transcript.md`, and a `cover.png`) is written
next to a local input file, or to `./<title-slug>/` for a YouTube URL.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--title` | from filename/video | Book title |
| `--cover` | auto-generated | Path to a custom cover image |
| `--cover-method` | `auto` | `auto`/`pillow` (Pillow) or `none` |
| `--output` | input dir / slug | Output directory |
| `--css` | built-in | Custom EPUB stylesheet |
| `--language` | `en` | Transcript language for YouTube |

## Input format

The cleaner understands three line shapes and falls through gracefully:

```
**00:01:23**: >> Alice: A timestamped speaker line.
**00:01:27**: A continuation line (timestamp only).
>> Bob: A speaker line without a timestamp.
Plain prose with no markers is kept too.
```

## Supported YouTube URLs

`watch?v=`, `youtu.be/`, `/embed/`, `/shorts/`, or a bare 11-character video ID.

## Requirements

- `pandoc` — builds the EPUB
- Python 3.10+ with `Pillow` — cover generation
- `youtube-transcript-api` — only for YouTube URLs
- `yt-dlp` *(optional)* — better YouTube metadata; falls back to an HTML scrape

## License

MIT — see [LICENSE](LICENSE).
