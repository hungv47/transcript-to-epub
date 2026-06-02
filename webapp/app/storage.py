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
    checkout_session_id: str | None = None
    subscription_id: str | None = None
    polar_customer_id: str | None = None
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


def _subscribers_path() -> Path:
    return config.JOBS_DIR / "subscribers.json"


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


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
    fields = set(Job.__dataclass_fields__)
    return Job(**{k: v for k, v in data.items() if k in fields})


def _read_subscribers() -> dict:
    p = _subscribers_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_subscribers(data: dict) -> None:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _subscribers_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def subscriber_active(email: str | None) -> bool:
    key = normalize_email(email)
    if not key:
        return False
    rec = _read_subscribers().get(key) or {}
    return bool(rec.get("active"))


def subscriber_record(email: str | None) -> dict:
    """The stored subscriber record for an email (subscription_id, customer_id,
    active flag), or an empty dict."""
    key = normalize_email(email)
    if not key:
        return {}
    return _read_subscribers().get(key) or {}


def jobs_for_email(email: str | None, limit: int | None = None) -> list[Job]:
    """All jobs attributed to this email, newest first. Scans JOBS_DIR — fine
    for the MVP's volume; revisit with a per-email index if jobs grow large."""
    key = normalize_email(email)
    if not key or not config.JOBS_DIR.exists():
        return []
    jobs: list[Job] = []
    for child in config.JOBS_DIR.iterdir():
        if not child.is_dir():
            continue
        job = load(child.name)
        if job and normalize_email(job.email) == key:
            jobs.append(job)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[:limit] if limit else jobs


def mark_subscriber_active(
    email: str | None,
    *,
    customer_id: str | None = None,
    subscription_id: str | None = None,
    checkout_id: str | None = None,
) -> None:
    key = normalize_email(email)
    if not key:
        return
    data = _read_subscribers()
    rec = data.get(key, {})
    rec.update({
        "email": key,
        "active": True,
        "customer_id": customer_id or rec.get("customer_id"),
        "subscription_id": subscription_id or rec.get("subscription_id"),
        "checkout_id": checkout_id or rec.get("checkout_id"),
        "updated_at": time.time(),
    })
    data[key] = rec
    _write_subscribers(data)


def mark_subscriber_inactive(email: str | None = None, *, subscription_id: str | None = None) -> None:
    data = _read_subscribers()
    keys: list[str] = []
    if email:
        keys.append(normalize_email(email))
    if subscription_id:
        keys.extend(
            key for key, rec in data.items()
            if rec.get("subscription_id") == subscription_id
        )
    for key in set(k for k in keys if k):
        if key in data:
            data[key]["active"] = False
            data[key]["updated_at"] = time.time()
    if keys:
        _write_subscribers(data)
