"""Filesystem-backed job store. No database — one directory per job.

A job is a folder under JOBS_DIR named by an unguessable id. ``meta.json`` holds
the original inputs (so the paid edition can be rebuilt on payment), status, and
a separate download token that gates the paid bundle. Survives restarts; good
enough for the validation MVP.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config


@dataclass
class Job:
    id: str
    title: str
    author: str | None
    source_url: str | None
    fmt: str
    raw_text: str
    paid: bool = False
    email: str | None = None
    accent: str = "#7F1D1D"
    download_token: str | None = None
    stripe_session_id: str | None = None
    # Outputs as {kind: filename}, e.g. {"epub": "book.epub"}.
    preview_outputs: dict = field(default_factory=dict)
    paid_outputs: dict = field(default_factory=dict)
    word_count: int = 0
    cover_prompt: str = ""
    created_at: float = field(default_factory=lambda: time.time())

    @property
    def dir(self) -> Path:
        return config.JOBS_DIR / self.id

    @property
    def preview_dir(self) -> Path:
        return self.dir / "preview"

    @property
    def paid_dir(self) -> Path:
        return self.dir / "paid"


def _meta_path(job_id: str) -> Path:
    return config.JOBS_DIR / job_id / "meta.json"


def new_job(*, title: str, author: str | None, source_url: str | None,
            fmt: str, raw_text: str) -> Job:
    job = Job(
        id=secrets.token_urlsafe(12),
        title=title,
        author=author,
        source_url=source_url,
        fmt=fmt,
        raw_text=raw_text,
        # Mint the paid-download token up front so concurrent fulfillments
        # (webhook + success-page poll) can't mint two and invalidate each
        # other. The token gates nothing until job.paid flips true.
        download_token=secrets.token_urlsafe(16),
    )
    job.dir.mkdir(parents=True, exist_ok=True)
    save(job)
    return job


def save(job: Job) -> None:
    job.dir.mkdir(parents=True, exist_ok=True)
    _meta_path(job.id).write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")


def load(job_id: str) -> Job | None:
    # Defend against path traversal in the id.
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        return None
    p = _meta_path(job_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return Job(**data)
