"""Sample library — original, zero-IP-risk demo books.

These are original works written for TalkToBook (fictional authors, no third-party
content), built with the same engine at paid quality (no watermark, designed
cover) so visitors can download and read a real output before trying the tool.

We never host third-party / user content as samples — that would make us a
publisher of others' IP rather than a tool. See terms.html.
"""

from __future__ import annotations

from pathlib import Path

from . import config, engine

SRC_DIR = config.BASE_DIR / "samples"

# Authored for TalkToBook. Original content, released for demo use.
SAMPLES = [
    {
        "slug": "the-quiet-tool",
        "title": "The Quiet Tool",
        "author": "Ada & Grace",
        "kind": "Interview",
        "blurb": "Two builders on why the best tools disappear into the work.",
        "src": "the-quiet-tool.md",
    },
    {
        "slug": "on-finishing",
        "title": "On Finishing",
        "author": "Marin Vale",
        "kind": "Solo talk",
        "blurb": "A short talk on shipping the work instead of polishing it forever.",
        "src": "on-finishing.md",
    },
    {
        "slug": "notes-from-a-long-walk",
        "title": "Notes from a Long Walk",
        "author": "Devi Rao & Tomas Lind",
        "kind": "Interview",
        "blurb": "A conversation on walking, attention, and where ideas come from.",
        "src": "notes-from-a-long-walk.md",
    },
]

_manifest: list[dict] | None = None


def _build_one(s: dict, dest_root: Path) -> dict:
    d = dest_root / s["slug"]
    epub = d / "book.epub"
    if not epub.exists():
        raw = (SRC_DIR / s["src"]).read_text(encoding="utf-8")
        engine.generate(
            d, raw_text=raw, fmt="md",
            title=s["title"], author=s["author"], source_url=None, paid=True,
        )
    item = {k: s[k] for k in ("slug", "title", "author", "kind", "blurb")}
    item["epub"] = f"/api/sample/{s['slug']}/book.epub"
    item["cover"] = f"/api/sample/{s['slug']}/cover.png" if (d / "cover.png").exists() else None
    item["pdf"] = f"/api/sample/{s['slug']}/book.pdf" if (d / "book.pdf").exists() else None
    return item


def get_manifest() -> list[dict]:
    """Build (once) and return the sample library manifest. Degrades to []."""
    global _manifest
    if _manifest is not None:
        return _manifest
    dest = config.JOBS_DIR / "_samples"
    out: list[dict] = []
    for s in SAMPLES:
        try:
            out.append(_build_one(s, dest))
        except engine.EngineError:
            continue  # missing pandoc etc. — skip rather than crash
    _manifest = out
    return out


def file_for(slug: str, name: str) -> Path | None:
    """Resolve a sample file path with slug/name validation."""
    if slug not in {s["slug"] for s in SAMPLES}:
        return None
    if name not in {"book.epub", "book.pdf", "cover.png"}:
        return None
    p = config.JOBS_DIR / "_samples" / slug / name
    return p if p.exists() else None
