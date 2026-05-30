# transcript-to-epub

Turn a spoken-word transcript — from a **YouTube URL** or a **local timestamped
markdown file** — into a calm, designed, **attributed** EPUB reading edition.

Every edition is **unofficial** and credits the original creators by full name at
the very beginning. It claims **no copyright** over the source material.

<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/809a265e-e607-413f-a903-4516c9c5f1e4" />
<img width="1108" height="830" alt="image" src="https://github.com/user-attachments/assets/b4a14df1-a82f-4053-9fe3-deba4d1f6923" />

Works as a standalone Python script or as a [Claude Code](https://docs.claude.com/en/docs/claude-code) skill (`SKILL.md` included).

## Install

```bash
brew install pandoc
pip3 install Pillow youtube-transcript-api
# yt-dlp is optional but gives more reliable YouTube title/channel:
brew install yt-dlp
```

To use it as a Claude Code skill, copy this folder into your skills directory
(e.g. `~/.claude/skills/transcript-to-epub/`).

## Requirements

- `python3` and `pandoc` on PATH (pandoc builds the EPUB).
- YouTube input: `youtube-transcript-api` (no API key needed).
- Pillow cover (`--cover-method pillow`, or `auto` when Pillow is present): `Pillow`.
- `yt-dlp` *(optional)* — better YouTube metadata; falls back to an HTML scrape.

## Quick start

```bash
python3 scripts/build.py examples/sample-transcript.md
```

Writes `book.md` and `book.epub` next to the input.

## Workflow

```
input (YouTube URL | local .md)
  -> extract raw transcript
  -> clean to reading markdown (strip timestamps + >> markers, merge paragraphs)
  -> cover (Pillow auto | prompt loop | user-supplied | none)
  -> compile designed EPUB
```

1. **Input** — a YouTube URL (auto-fetches the transcript and channel name) or a
   local timestamped transcript `.md`.
2. **Extract** the raw transcript text.
3. **Clean** — strip timestamps and `>>` speaker markers, merge into paragraphs.
4. **Cover** — choose one path (see [Cover options](#cover-options)).
5. **Compile** to a designed EPUB.

**Outputs (both, always):**

- `<output>/book.md` — the assembled clean Markdown book (attribution + body).
- `<output>/book.epub` — the designed EPUB.

The CLI prints `Wrote: <path>` for each. (A Pillow cover also writes `cover.png`.)

## CLI

```
python3 scripts/build.py <input> [options]
```

`<input>` is a YouTube URL **or** a path to a local `.md` transcript.

| Flag | Default | Meaning |
|------|---------|---------|
| `input` (positional) | — | YouTube URL or local `.md` transcript path |
| `--title` | derived from filename or video title | Book title |
| `--speakers` | auto-detected | Comma-separated speaker names; overrides the auto-detected byline |
| `--source-url` | canonical YouTube URL for URL input; empty for file input | Link to the original; used in attribution + pandoc metadata |
| `--cover` | — | Path to a user-supplied cover image (png/jpeg) |
| `--cover-method` | `auto` | One of `auto`, `pillow`, `prompt`, `none` |
| `--output` | input file's dir, or a title-slug dir for a YouTube URL | Output directory |
| `--language` | `en` | Transcript language code (used for YouTube) |
| `--css` | built-in stylesheet | Custom EPUB stylesheet |

### Cover options

`--cover-method` controls how the cover is produced:

- `auto` — Pillow-generated brand cover if Pillow is installed; otherwise no cover.
- `pillow` — force the Pillow-generated brand cover.
- `prompt` — print a ready-to-paste, brand-aligned AI image-generation prompt to
  stdout, then build **without** a cover. Generate the art in any image tool and
  re-run with `--cover <file>`.
- `none` — no cover.

You can always skip the methods above and pass your own image with
`--cover path/to/cover.png`.

## Attribution & copyright

This is a hard requirement of the tool, not an option.

Every book **always** credits the original creators by full name at the very
beginning, before any transcript content. The editions are **unofficial** and
**claim no copyright** over the source material.

Each book opens with an attribution front-matter block, wrapped in
`<!-- t2e:attribution:start -->` / `<!-- t2e:attribution:end -->` markers (pandoc
drops these HTML comments from the rendered EPUB):

- H1 title
- credit line: `An unofficial reading edition of a conversation by <creators>.`
- source line: `Original source: <source_url>` (omitted only when the URL is unknown)
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

Override the byline if you want named speakers instead of the channel:

```bash
python3 scripts/build.py "https://www.youtube.com/watch?v=VIDEO_ID" \
  --speakers "Ada Lovelace, Grace Hopper"
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

## Input format

A local transcript is markdown with an H1 title and timestamped `>>`-marked
turns. See `examples/sample-transcript.md`. The cleaner understands several line
shapes and falls through gracefully:

```
**00:01:23**: >> Alice: A timestamped speaker line.
**00:01:27**: A continuation line (timestamp only).
>> Bob: A speaker line without a timestamp.
Plain prose with no markers is kept too.
```

Timestamps (`**HH:MM:SS**`) and `>>` markers are stripped during cleaning; turns
are merged into reading paragraphs.

## Supported YouTube URLs

`watch?v=`, `youtu.be/`, `/embed/`, `/shorts/`, or a bare 11-character video ID.

## License

MIT — see [LICENSE](LICENSE).
