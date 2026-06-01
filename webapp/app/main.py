"""TalkToBook — FastAPI service wrapping the transcript-to-epub engine.

Flow: YouTube URL or transcript upload → free EPUB preview (watermarked, plain
cover) → $7/month creator plan → clean, branded EPUB + PDF + Kindle. No
accounts yet; jobs live on disk keyed by an unguessable id, and active creator
plans are tracked by email.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, engine, payments, storage

app = FastAPI(title=f"{config.APP_NAME} API")

STATIC_DIR = config.BASE_DIR / "static"
config.JOBS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
# Chrome's "insecure file" warning on .epub downloads and most browser
# hardening checks (HSTS preload, mixed-content detection) key off these
# response headers. Sending them on every response is cheap and removes a
# whole class of "why is the site warning me" reports.
#   - HSTS is only set when the request is actually served over HTTPS (or
#     arrived via a proxy that says so), so dev on http://localhost works.
#   - Cross-Origin-Resource-Policy: same-origin is what stops another site
#     from embedding our download URLs in an <a download>.

_DOWNLOAD_HARDENING = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


def _is_local_request(request: Request) -> bool:
    host = (request.url.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _https_redirect_url(request: Request) -> str:
    req = urlsplit(str(request.url))
    public = urlsplit(config.PUBLIC_URL)
    netloc = public.netloc if public.scheme == "https" and public.netloc else req.netloc
    return urlunsplit(("https", netloc, req.path, req.query, req.fragment))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if config.FORCE_HTTPS and not _is_https(request) and not _is_local_request(request):
        return RedirectResponse(_https_redirect_url(request), status_code=308)
    response = await call_next(request)
    for k, v in _DOWNLOAD_HARDENING.items():
        response.headers.setdefault(k, v)
    if _is_https(request):
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
        response.headers.setdefault("Content-Security-Policy", "upgrade-insecure-requests")
    if "server" in response.headers:
        del response.headers["server"]
    # Uvicorn re-adds `server: uvicorn` after middleware runs, so set a custom
    # value here so the framework doesn't leak through.
    response.headers["server"] = "TalkToBook"
    return response

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


def _valid_image(data: bytes) -> bool:
    """True if bytes decode as an image — so a bad upload can't fail the paid
    build later. If Pillow is unavailable, don't block (engine retries coverless)."""
    try:
        from PIL import Image
        Image.open(io.BytesIO(data)).verify()
        return True
    except ImportError:
        return True
    except Exception:
        return False


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


def _download_url(job: storage.Job, kind: str, token: str) -> str:
    """Build a download URL for a file kind. token="preview" serves the free
    EPUB; the job's download_token serves the gated paid files."""
    name = DOWNLOAD_NAMES[kind][0]
    return f"/d/{job.id}/{token}/{name}"


def _job_public(job: storage.Job) -> dict:
    out = {
        "job_id": job.id,
        "title": job.title,
        "author": job.author,
        "word_count": job.word_count,
        "paid": job.paid,
        "cover_prompt": job.cover_prompt,
        "preview": {k: _download_url(job, k, "preview") for k in job.preview_outputs},
    }
    if job.paid and job.download_token:
        out["downloads"] = {k: _download_url(job, k, job.download_token) for k in job.paid_outputs}
    return out


async def fulfill(job: storage.Job) -> None:
    """Build the paid edition and gate it behind a fresh download token."""
    if job.paid and job.paid_outputs:
        return
    cover_path = next(iter(job.dir.glob("uploaded_cover.*")), None)
    result = await asyncio.to_thread(
        engine.generate,
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


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> PlainTextResponse:
    """Served from PUBLIC_URL so the Sitemap directive points at the live host."""
    origin = (config.PUBLIC_URL or "").rstrip("/")
    body = (STATIC_DIR / "robots.txt").read_text(encoding="utf-8")
    if origin and "Sitemap:" in body:
        body = body.replace("https://talktobook.com", origin)
    return PlainTextResponse(body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap() -> Response:
    """Served from PUBLIC_URL so every <loc> is the live origin, not localhost."""
    origin = (config.PUBLIC_URL or "").rstrip("/")
    body = (STATIC_DIR / "sitemap.xml").read_text(encoding="utf-8")
    if origin:
        body = body.replace("https://talktobook.com", origin)
    return Response(content=body, media_type="application/xml")


@app.get("/healthz")
async def healthz():
    """Liveness/readiness probe for the host platform."""
    return {"status": "ok", "capabilities": engine.capabilities()}


@app.get("/api/config")
async def public_config():
    return {
        "app_name": config.APP_NAME,
        "price_cents": config.UNLOCK_PRICE_CENTS,
        "currency": config.CURRENCY,
        "payment_provider": "polar",
        "payments_enabled": config.payments_enabled(),
        "allow_free_unlock": config.ALLOW_FREE_UNLOCK,
        "capabilities": engine.capabilities(),
        "contact_email": config.CONTACT_EMAIL,
        "dmca_email": config.DMCA_EMAIL,
    }


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
    source_url = (source_url or "").strip()
    author_hint = None
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
    elif source_url:
        if not engine.is_youtube_source(source_url):
            raise HTTPException(400, "Only YouTube URLs are supported right now. Upload a transcript file for other sources.")
        try:
            fetched = await asyncio.to_thread(engine.fetch_youtube_source, source_url)
        except engine.TranscriptFetchError as e:
            raise HTTPException(400, str(e))
        raw_text = fetched["raw_text"]
        title = title or fetched["title"]
        author_hint = fetched["author"]
        source_url = fetched["source_url"]

    raw_text = raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Enter a YouTube URL or upload a transcript file.")
    if len(raw_text) > config.MAX_TRANSCRIPT_CHARS:
        raise HTTPException(400, "Transcript is too long for the preview.")

    fmt = detect_format(raw_text, filename)
    # Author is auto-detected from the transcript and not user-editable — the
    # original creators are always credited (falling back to a generic credit).
    title_d, author_d = engine.derive_metadata(raw_text, fmt, title, author_hint)
    author_d = author_d or engine.UNKNOWN_CREATORS

    job = storage.new_job(
        title=title_d, author=author_d,
        source_url=source_url or None,
        fmt=fmt, raw_text=raw_text,
    )
    try:
        result = await asyncio.to_thread(
            engine.generate,
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
            if len(data) > config.MAX_UPLOAD_BYTES:
                raise HTTPException(400, "Cover image is too large.")
            if not _valid_image(data):
                raise HTTPException(400, "That cover image couldn't be read. Use a valid PNG or JPG.")
            for old in job.dir.glob("uploaded_cover.*"):
                old.unlink()
            (job.dir / f"uploaded_cover.{ext}").write_bytes(data)
    storage.save(job)
    _event("unlock_click", job_id=job.id, email=bool(job.email), provider="polar", live=config.payments_enabled())

    # Already paid (idempotent re-click).
    if job.paid:
        return _job_public(job)

    # Active creator plan: email-linked unlimited clean editions.
    if storage.subscriber_active(job.email):
        await fulfill(job)
        return _job_public(job)

    # Dev escape hatch: fulfill without paying.
    if config.ALLOW_FREE_UNLOCK and not config.payments_enabled():
        await fulfill(job)
        return _job_public(job)

    try:
        result = payments.create_checkout(job, job.email or "")
    except payments.PaymentError as e:
        raise HTTPException(502, str(e))
    if result.get("url"):
        job.checkout_session_id = result.get("checkout_id")
        storage.save(job)
        return {"checkout_url": result["url"]}

    # Intent-capture mode: no live payments yet. Record the demand signal —
    # the lead email is persisted on the job record, not in the funnel log.
    _event("unlock_intent", job_id=job.id, email=bool(job.email))
    return {
        "intent": True,
        "message": "Checkout is launching shortly. We saved your email and will send your creator plan link when it goes live.",
    }


def _event_email(data: dict) -> str | None:
    customer = data.get("customer") or {}
    return data.get("customer_email") or data.get("email") or customer.get("email")


async def _activate_subscription_for_job(data: dict) -> None:
    product_id = data.get("product_id") or (data.get("product") or {}).get("id")
    if product_id and product_id != config.POLAR_PRODUCT_ID:
        return
    metadata = data.get("metadata") or {}
    job_id = metadata.get("job_id")
    checkout_id = data.get("checkout_id") or data.get("id")
    subscription = data.get("subscription") or {}
    subscription_id = data.get("subscription_id") or data.get("id") or subscription.get("id")
    customer = data.get("customer") or {}
    email = _event_email(data) or metadata.get("email")

    storage.mark_subscriber_active(
        email,
        customer_id=data.get("customer_id") or customer.get("id"),
        subscription_id=subscription_id,
        checkout_id=checkout_id,
    )

    job = storage.load(job_id) if job_id else None
    if not job and checkout_id:
        # Some webhook payloads carry metadata on the checkout/order, while the
        # success-page fallback can reconcile directly from the checkout record.
        checkout_job_id = payments.checkout_job_id(checkout_id)
        job = storage.load(checkout_job_id) if checkout_job_id else None
    if job:
        job.checkout_session_id = checkout_id or job.checkout_session_id
        job.subscription_id = subscription_id or job.subscription_id
        job.polar_customer_id = data.get("customer_id") or customer.get("id") or job.polar_customer_id
        job.email = job.email or email
        storage.save(job)
        await fulfill(job)


@app.post("/api/webhook")
async def polar_webhook(request: Request):
    payload = await request.body()
    event = payments.verify_webhook(payload, request.headers)
    if event is None:
        raise HTTPException(400, "Invalid webhook signature.")
    event_type = event.get("type")
    data = event.get("data") or {}

    if event_type in {"order.paid", "subscription.active", "subscription.uncanceled"}:
        await _activate_subscription_for_job(data)
    elif event_type == "subscription.revoked":
        storage.mark_subscriber_inactive(_event_email(data), subscription_id=data.get("id"))
    elif event_type == "customer.state_changed":
        email = data.get("email")
        active = [
            s for s in data.get("active_subscriptions", [])
            if s.get("product_id") == config.POLAR_PRODUCT_ID
        ]
        if active:
            s = active[0]
            storage.mark_subscriber_active(
                email,
                customer_id=data.get("id"),
                subscription_id=s.get("id"),
                checkout_id=s.get("checkout_id"),
            )
        else:
            storage.mark_subscriber_inactive(email)
    return JSONResponse({"received": True})


@app.get("/api/job/{job_id}")
async def job_status(job_id: str, checkout_id: str | None = None, session_id: str | None = None):
    job = storage.load(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    # Reconcile a returning Checkout customer if the webhook hasn't landed yet.
    # The checkout must belong to THIS job (metadata binding), so a paid checkout
    # for one job can't be replayed to unlock another.
    checkout_id = checkout_id or session_id
    if not job.paid and checkout_id and payments.checkout_job_id(checkout_id) == job.id:
        checkout = payments.get_checkout(checkout_id) or {}
        job.checkout_session_id = checkout_id
        job.subscription_id = checkout.get("subscription_id") or job.subscription_id
        job.polar_customer_id = checkout.get("customer_id") or job.polar_customer_id
        if job.email:
            storage.mark_subscriber_active(
                job.email,
                customer_id=job.polar_customer_id,
                subscription_id=job.subscription_id,
                checkout_id=checkout_id,
            )
        storage.save(job)
        await fulfill(job)
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
        if not (job.paid and job.download_token
                and secrets.compare_digest(token, job.download_token)):
            raise HTTPException(403, "This download is locked. Complete checkout to unlock.")
        path = job.paid_dir / name

    if not path.exists():
        raise HTTPException(404, "Not found.")
    media = next((m for n, m in DOWNLOAD_NAMES.values() if n == name), "application/octet-stream")
    safe_title = re.sub(r"[^\w\- ]", "", job.title)[:60].strip() or "book"
    return FileResponse(
        path,
        media_type=media,
        filename=f"{safe_title}{Path(name).suffix}",
        headers={
            # Stop third-party sites from embedding our download URLs in their
            # own pages. Also makes Chrome's "insecure file" heuristic happier
            # because the file is explicitly same-origin-gated.
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Description": "File Transfer",
            "X-Content-Type-Options": "nosniff",
        },
    )


# Mount static assets last so it doesn't shadow API routes.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
