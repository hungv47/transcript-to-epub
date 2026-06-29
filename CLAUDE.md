# CLAUDE.md — transcript-to-epub (talktobook)

Turns a spoken-word transcript (a **YouTube URL** or a **local timestamped markdown file**) into a
calm, designed, **attributed** EPUB reading edition. Every edition is unofficial, credits the
original creators by name, and claims no copyright over the source.

Runs three ways: a **standalone Python script**, a **Claude Code skill** (`SKILL.md`), and a
**web app** (`webapp/`, deployed on Railway — `railway.json`). Code-only repo (experimental); no
`ops/` business folder yet.

## Run

```bash
brew install pandoc            # required
pip3 install Pillow youtube-transcript-api
brew install yt-dlp            # optional, better YouTube title/channel
```

- CLI entry: `scripts/` (see `README.md`). Skill: copy the folder into `~/.claude/skills/`.
- Web app: `webapp/` (serves HTML editions; honors `PUBLIC_URL` for canonical/OG/JSON-LD URLs).

## Shape

- `scripts/` — the converter pipeline. `brand/` + `DESIGN.md` — edition design/typography.
- `examples/` — sample inputs/outputs. `LICENSE` — repo license (source material stays the creators').

## Conventions

- Attribution-first and copyright-clean by design — preserve the creator-credit + no-copyright framing.
- Match existing Python style; keep dependencies minimal. Ship only when the whole thing is done.
