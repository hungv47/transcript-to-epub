"""TalkToBook — FastAPI service wrapping the transcript-to-epub engine.

Flow: paste/upload a transcript → free preview EPUB (watermarked, plain cover)
→ $9 unlock → clean, branded EPUB + PDF + Kindle. No accounts; jobs live on disk
keyed by an unguessable id, paid files gated behind a separate download token.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, engine, payments, samples, storage

app = FastAPI(title=f"{config.APP_NAME} API")

STATIC_DIR = config.BASE_DIR / "static"
config.JOBS_DIR.mkdir(parents=True, exist_ok=True)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DOWNLOAD_NAMES = {
    "epub": ("book.epub", "application/epub+zip"),
    "pdf": ("book.pdf", "application/pdf"),
    "azw3": ("book.azw3", "application/vnd.amazon.ebook"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "on", "yes")


def _event(kind: str, **fields) -> None:
    """Append a funnel event for validation instrumentation."""
    rec = {"ts": round(time.time(), 3), "event": kind, **fields}
    with (config.JOBS_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def detect_format(text: str, filename: str | None) -> str:
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in config.ALLOWED_EXTS:
            return "vtt" if ext == "vtt" else ext
    # Auto-detect subtitle paste by its timecode arrows.
    if text.count("-->") >= 2:
        return "vtt"
    return "txt"


def _accent(raw: str | None) -> str:
    raw = (raw or "").strip()
    return raw if HEX_RE.match(raw) else engine.BRAND_ACCENT


def _preview_url(job: storage.Job, kind: str) -> str:
    name = DOWNLOAD_NAMES[kind][0]
    return f"/d/{job.id}/preview/{name}"


def _paid_url(job: storage.Job, kind: str) -> str:
    name = DOWNLOAD_NAMES[kind][0]
    return f"/d/{job.id}/{job.download_token}/{name}"


def _job_public(job: storage.Job) -> dict:
    out = {
        "job_id": job.id,
        "title": job.title,
        "author": job.author,
        "word_count": job.word_count,
        "paid": job.paid,
        "cover_prompt": job.cover_prompt,
        "preview": {k: _preview_url(job, k) for k in job.preview_outputs},
    }
    if job.paid and job.download_token:
        out["downloads"] = {k: _paid_url(job, k) for k in job.paid_outputs}
    return out


def fulfill(job: storage.Job) -> None:
    """Build the paid edition and gate it behind a fresh download token."""
    if job.paid and job.paid_outputs:
        return
    cover_path = next(iter(job.dir.glob("uploaded_cover.*")), None)
    result = engine.generate(
        job.paid_dir,
        raw_text=job.raw_text,
        fmt=job.fmt,
        title=job.title,
        author=job.author,
        source_url=job.source_url,
        paid=True,
        accent=job.accent,
        cover_image=cover_path,
    )
    job.paid = True
    job.paid_outputs = result["outputs"]
    job.download_token = job.download_token or storage.secrets.token_urlsafe(16)
    storage.save(job)
    _event("payment_fulfilled", job_id=job.id, formats=list(job.paid_outputs))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/success")
async def success():
    return FileResponse(STATIC_DIR / "success.html")


@app.get("/terms")
async def terms():
    return FileResponse(STATIC_DIR / "terms.html")


@app.get("/api/config")
async def public_config():
    return {
        "app_name": config.APP_NAME,
        "price_cents": config.UNLOCK_PRICE_CENTS,
        "currency": config.CURRENCY,
        "stripe_enabled": config.stripe_enabled(),
        "allow_free_unlock": config.ALLOW_FREE_UNLOCK,
        "capabilities": engine.capabilities(),
        "contact_email": config.CONTACT_EMAIL,
        "dmca_email": config.DMCA_EMAIL,
    }


# ---------------------------------------------------------------------------
# Sample library (original, zero-IP-risk demo books)
# ---------------------------------------------------------------------------

@app.get("/api/samples")
async def list_samples():
    return {"samples": samples.get_manifest()}


@app.get("/api/sample/{slug}/{name}")
async def sample_file(slug: str, name: str):
    path = samples.file_for(slug, name)
    if not path:
        raise HTTPException(404, "Not found.")
    media = {
        "book.epub": "application/epub+zip",
        "book.pdf": "application/pdf",
        "cover.png": "image/png",
    }.get(name, "application/octet-stream")
    # Inline for cover thumbnails; download for the book files.
    if name == "cover.png":
        return FileResponse(path, media_type=media)
    safe = re.sub(r"[^\w\- ]", "", slug)[:60] or "sample"
    return FileResponse(path, media_type=media, filename=f"{safe}{Path(name).suffix}")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@app.post("/api/preview")
async def create_preview(
    title: str = Form(""),
    source_url: str = Form(""),
    owns: str = Form(""),
    transcript: str = Form(""),
    file: UploadFile | None = File(None),
):
    if not _bool(owns):
        raise HTTPException(400, "You must confirm you own or have rights to this content.")

    raw_text = transcript or ""
    filename = None
    if file is not None and file.filename:
        filename = file.filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in config.ALLOWED_EXTS:
            raise HTTPException(400, f"Unsupported file type .{ext}. Use: {', '.join(sorted(config.ALLOWED_EXTS))}.")
        data = await file.read()
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(400, "File too large.")
        raw_text = data.decode("utf-8", errors="replace")

    raw_text = raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Paste a transcript or upload a file.")
    if len(raw_text) > config.MAX_TRANSCRIPT_CHARS:
        raise HTTPException(400, "Transcript is too long for the preview.")

    fmt = detect_format(raw_text, filename)
    # Author is auto-detected from the transcript and not user-editable — the
    # original creators are always credited (falling back to a generic credit).
    title_d, author_d = engine.derive_metadata(raw_text, fmt, title, None)
    author_d = author_d or engine.UNKNOWN_CREATORS

    job = storage.new_job(
        title=title_d, author=author_d,
        source_url=(source_url or "").strip() or None,
        fmt=fmt, raw_text=raw_text,
    )
    try:
        result = engine.generate(
            job.preview_dir, raw_text=raw_text, fmt=fmt,
            title=title_d, author=author_d,
            source_url=job.source_url, paid=False,
        )
    except engine.EngineError as e:
        raise HTTPException(422, f"Could not build the book: {e}")

    job.preview_outputs = result["outputs"]
    job.word_count = result["word_count"]
    job.cover_prompt = result["cover_prompt"]
    storage.save(job)
    _event("preview_created", job_id=job.id, words=job.word_count, fmt=fmt)

    return _job_public(job)


# ---------------------------------------------------------------------------
# Unlock / payment
# ---------------------------------------------------------------------------

@app.post("/api/unlock")
async def unlock(
    job_id: str = Form(...),
    email: str = Form(""),
    accent: str = Form(""),
    cover: UploadFile | None = File(None),
):
    job = storage.load(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")

    job.email = (email or "").strip() or job.email
    job.accent = _accent(accent)

    if cover is not None and cover.filename:
        ext = cover.filename.rsplit(".", 1)[-1].lower() if "." in cover.filename else "png"
        if ext in ("png", "jpg", "jpeg"):
            data = await cover.read()
            if len(data) <= config.MAX_UPLOAD_BYTES:
                for old in job.dir.glob("uploaded_cover.*"):
                    old.unlink()
                (job.dir / f"uploaded_cover.{ext}").write_bytes(data)
    storage.save(job)
    _event("unlock_click", job_id=job.id, email=bool(job.email), stripe=config.stripe_enabled())

    # Already paid (idempotent re-click).
    if job.paid:
        return _job_public(job)

    # Dev escape hatch: fulfill without paying.
    if config.ALLOW_FREE_UNLOCK and not config.stripe_enabled():
        fulfill(job)
        return _job_public(job)

    result = payments.create_checkout(job, job.email or "")
    if result.get("url"):
        job.stripe_session_id = result.get("session_id")
        storage.save(job)
        return {"checkout_url": result["url"]}

    # Intent-capture mode: no live payments yet. Record the demand signal.
    _event("unlock_intent", job_id=job.id, email=job.email or "", title=job.title)
    return {
        "intent": True,
        "message": "Payments are launching shortly — we saved your email and will send your unlock link the moment they go live.",
    }


@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = payments.verify_webhook(payload, sig)
    if event is None:
        raise HTTPException(400, "Invalid webhook signature.")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        job_id = (session.get("metadata") or {}).get("job_id")
        job = storage.load(job_id) if job_id else None
        if job:
            job.stripe_session_id = session.get("id")
            job.email = job.email or session.get("customer_details", {}).get("email")
            fulfill(job)
    return JSONResponse({"received": True})


@app.get("/api/job/{job_id}")
async def job_status(job_id: str, session_id: str | None = None):
    job = storage.load(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    # Reconcile a returning Checkout customer if the webhook hasn't landed yet.
    if not job.paid and session_id and payments.session_is_paid(session_id):
        fulfill(job)
    return _job_public(job)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

@app.get("/d/{job_id}/{token}/{name}")
async def download(job_id: str, token: str, name: str):
    job = storage.load(job_id)
    if not job:
        raise HTTPException(404, "Not found.")
    if name not in {n for n, _ in DOWNLOAD_NAMES.values()}:
        raise HTTPException(404, "Not found.")

    if token == "preview":
        path = job.preview_dir / name
    else:
        if not (job.paid and job.download_token and token == job.download_token):
            raise HTTPException(403, "This download is locked. Complete checkout to unlock.")
        path = job.paid_dir / name

    if not path.exists():
        raise HTTPException(404, "Not found.")
    media = next((m for n, m in DOWNLOAD_NAMES.values() if n == name), "application/octet-stream")
    safe_title = re.sub(r"[^\w\- ]", "", job.title)[:60].strip() or "book"
    return FileResponse(path, media_type=media, filename=f"{safe_title}{Path(name).suffix}")


# Mount static assets last so it doesn't shadow API routes.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
