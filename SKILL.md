---
name: transcript-to-epub
description: "Turn a YouTube URL or a local timestamped transcript into a designed, attributed EPUB reading edition. Auto-detects speakers/channel, cleans timestamps, always credits the original creators, and builds both a clean Markdown book and a book.epub."
argument-hint: "<youtube-url|input.md> [--title <title>] [--speakers <names>] [--source-url <url>] [--cover <path>] [--cover-method auto|pillow|prompt|none]"
allowed-tools: Read, Write, Bash, Glob
metadata:
  version: "1.4.0"
---

# Transcript to EPUB

Turn a spoken-word transcript (a YouTube URL or a local timestamped markdown
file) into a calm, book-like EPUB — and **always** credit the original creators
with an explicit unofficial / no-copyright-claim notice.

## When To Use

- YouTube video URL → auto-fetch transcript + channel name → EPUB
- Raw transcript with `**HH:MM:SS**` timestamps → clean EPUB
- Podcast / interview transcripts with `>>` speaker markers → auto-detect speakers
- Any conversation transcript that should become a readable e-book

## When NOT To Use

- Already-formatted markdown → just use `pandoc` directly
- Video/audio with no captions → needs captions or a manual transcript
- Private/restricted YouTube videos → transcript won't be accessible

## Requirements

- `python3` and `pandoc` on PATH (pandoc builds the EPUB).
- YouTube input: `pip3 install youtube-transcript-api` (no API key needed).
- `--cover-method pillow` (and `auto` when Pillow is present): `pip3 install Pillow`.
- `yt-dlp` *(optional)* — more reliable YouTube title/channel; falls back to HTML scrape.

## CLI contract

```
python3 scripts/build.py <input> [options]
```

`<input>` is a YouTube URL **or** a path to a local `.md` transcript.

| Flag | Default | Meaning |
|------|---------|---------|
| `input` (positional) | — | YouTube URL or local `.md` transcript path |
| `--title` | derived from filename or video title | Book title |
| `--speakers` | auto-detected | Comma-separated names; overrides the auto-detected byline |
| `--source-url` | canonical YouTube URL for URL input; empty for file input | Link to the original; used in attribution + pandoc metadata |
| `--cover` | — | Path to a user-supplied cover image (png/jpeg) |
| `--cover-method` | `auto` | One of `auto`, `pillow`, `prompt`, `none` |
| `--output` | input file's dir, or a title-slug dir for a YouTube URL | Output directory |
| `--language` | `en` | Transcript language code (used for YouTube) |
| `--css` | built-in stylesheet | Custom EPUB stylesheet |

### `--cover-method` values

- `auto` — Pillow-generated brand cover if Pillow is installed; otherwise no cover.
- `pillow` — force the Pillow-generated brand cover.
- `prompt` — print a ready-to-paste AI image-generation prompt to stdout, then
  build **without** a cover. Re-run with `--cover <file>` once you have the image.
- `none` — no cover.

You can always skip the methods above and pass your own image with `--cover path/to/cover.png`.

## Workflow

1. **Input** — a YouTube URL (auto-fetch transcript + channel name) OR a local
   timestamped transcript `.md`.
2. **Extract** the raw transcript text.
3. **Clean** — strip timestamps and `>>` markers, merge lines into paragraphs.
4. **Cover** — pick one path:
   - Pillow brand cover (`auto` / `pillow`), or
   - `prompt` → get an AI-image prompt, generate the art in any image tool, then
     re-run with `--cover your.png`, or
   - user-supplied `--cover your.png|jpg` directly, or `none`.
5. **Compile** to a designed EPUB.

**Outputs (both, always):** `<output>/book.md` (the assembled clean Markdown
book) AND `<output>/book.epub`. The CLI prints `Wrote: <path>` for each. (Pillow
covers also write `cover.png`.)

## Attribution & copyright (hard requirement)

The skill **always** credits the original creators by full name at the very
beginning of the book, before any transcript content. The editions are
**unofficial** and claim **no copyright** over the source material.

Every book opens with an attribution front-matter block (wrapped in
`<!-- t2e:attribution:start -->` / `<!-- t2e:attribution:end -->` markers, which
pandoc drops from the EPUB):

- H1 title
- credit line: `An unofficial reading edition of a conversation by <creators>.`
- source line: `Original source: <source_url>` (omitted only if the URL is unknown)
- a blockquote disclaimer: this edition is unofficial; all rights to the original
  material belong to the original creators; this edition claims no copyright over
  the source; an invitation to support the creators at the source URL.

Rules the tool enforces:

- Credit is **never** silently dropped.
- If creators are unknown, the byline falls back to `the original creators`.
- If the URL is unknown, only the URL line is omitted.
- The same facts are written to EPUB metadata: `author=<creators>` plus a
  `rights`/`description` string naming the source and the non-ownership statement.
- The block appears in **both** the Markdown output and the EPUB.
- Re-running on an already-assembled `book.md` is idempotent — the attribution
  block is not duplicated.

## Examples

### YouTube URL

The canonical `https://www.youtube.com/watch?v=<id>` source URL is filled in
automatically; the channel name becomes the creator byline.

```bash
python3 scripts/build.py "https://www.youtube.com/watch?v=VIDEO_ID" \
  --title "The Craft Conversation" \
  --cover-method auto
```

### Local transcript with the cover-prompt loop

```bash
# 1. Print an AI image prompt and produce a no-cover build:
python3 scripts/build.py examples/sample-transcript.md \
  --speakers "Ada Lovelace, Grace Hopper" \
  --source-url "https://example.com/talk" \
  --cover-method prompt

# Copy the printed prompt into your AI image tool of choice,
# then save the result as cover.png.

# 2. Re-run with the generated image to get the final cover:
python3 scripts/build.py examples/sample-transcript.md \
  --speakers "Ada Lovelace, Grace Hopper" \
  --source-url "https://example.com/talk" \
  --cover cover.png
```

See `examples/sample-transcript.md` for a runnable local input.

## Supported YouTube URL formats

`watch?v=`, `youtu.be/`, `/embed/`, `/shorts/`, or a bare 11-character video ID.
