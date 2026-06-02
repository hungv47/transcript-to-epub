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

from . import config, engine, payments, session, storage

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
    # Health probes hit /healthz over plain HTTP on the host's internal network
    # (no x-forwarded-proto), so redirecting them to HTTPS makes the platform
    # healthcheck fail and the deploy never goes live. Exempt the health path.
    if (
        config.FORCE_HTTPS
        and request.url.path != "/healthz"
        and not _is_https(request)
        and not _is_local_request(request)
    ):
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


@app.get("/dashboard")
async def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


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


# Markdown docs for AI assistants and crawlers (AEO/SEO). Served at the root so
# URLs stay clean (/llms.txt, /product.md, ...). PUBLIC_URL is substituted so
# absolute links resolve to the live origin in any environment.
def _serve_doc(filename: str, media_type: str = "text/markdown; charset=utf-8") -> Response:
    origin = (config.PUBLIC_URL or "").rstrip("/")
    body = (STATIC_DIR / filename).read_text(encoding="utf-8")
    if origin:
        body = body.replace("https://talktobook.com", origin)
    return Response(content=body, media_type=media_type)


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt() -> Response:
    return _serve_doc("llms.txt", "text/plain; charset=utf-8")


@app.get("/product.md", include_in_schema=False)
async def product_md() -> Response:
    return _serve_doc("product.md")


@app.get("/pricing.md", include_in_schema=False)
async def pricing_md() -> Response:
    return _serve_doc("pricing.md")


@app.get("/faq.md", include_in_schema=False)
async def faq_md() -> Response:
    return _serve_doc("faq.md")


@app.get("/healthz")
async def healthz():
    """Liveness/readiness probe for the host platform."""
    return {"status": "ok", "capabilities": engine.capabilities()}


@app.get("/api/config")
async def public_config():
    return {
        "app_name": config.APP_NAME,
        "price_cents": config.UNLOCK_PRICE_CENTS,
        "price_annual_cents": config.PLAN_PRICE_ANNUAL_CENTS,
        "annual_enabled": bool(config.POLAR_PRODUCT_ID_ANNUAL),
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


@app.post("/api/checkout")
async def plan_checkout(interval: str = Form("monthly"), email: str = Form("")):
    """Start a Creator Plan checkout straight from the pricing section, with no
    preview job. The plan is email-linked; generating and unlocking later with
    the same email fulfills clean editions."""
    interval = "yearly" if interval == "yearly" else "monthly"
    _event("plan_checkout_click", interval=interval, email=bool(email), live=config.payments_enabled())
    try:
        result = payments.create_plan_checkout(interval, email)
    except payments.PaymentError as e:
        raise HTTPException(502, str(e))
    if result.get("url"):
        return {"checkout_url": result["url"]}
    _event("plan_checkout_intent", interval=interval, email=bool(email))
    return {
        "intent": True,
        "message": "Payments are launching shortly. Generate a free preview now, and we'll email your plan link when it goes live.",
    }


# ---------------------------------------------------------------------------
# Post-purchase dashboard (signed session, no accounts)
# ---------------------------------------------------------------------------

def _set_session_cookie(response: Response, request: Request, email: str) -> None:
    response.set_cookie(
        session.COOKIE_NAME,
        session.issue(email),
        max_age=session.max_age(),
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


@app.post("/api/session")
async def start_session(request: Request, checkout_id: str = Form(...)):
    """Establish a dashboard session from a verified Polar checkout. The success
    page calls this right after payment: we verify the checkout server-side,
    learn the email, mark the subscriber active (webhook-tolerant), and set a
    signed cookie. A still-pending checkout returns 202 so the client can retry."""
    checkout = payments.get_checkout(checkout_id)
    if not checkout:
        return JSONResponse({"authenticated": False, "pending": True}, status_code=202)
    metadata = checkout.get("metadata") or {}
    email = storage.normalize_email(checkout.get("customer_email") or metadata.get("email"))
    if not email:
        return JSONResponse({"authenticated": False}, status_code=409)
    storage.mark_subscriber_active(
        email,
        customer_id=checkout.get("customer_id"),
        subscription_id=checkout.get("subscription_id"),
        checkout_id=checkout_id,
    )
    _event("dashboard_session_start", email=True)
    resp = JSONResponse({"authenticated": True, "email": email})
    _set_session_cookie(resp, request, email)
    return resp


def _plan_status(rec: dict) -> dict:
    """Live plan status: prefer Polar's subscription record, fall back to the
    local active flag when payments are off or the fetch fails."""
    sub = payments.get_subscription(rec.get("subscription_id")) if rec.get("subscription_id") else None
    if sub:
        return {
            "active": sub.get("status") in {"active", "trialing"},
            "status": sub.get("status"),
            "interval": sub.get("recurring_interval"),
            "renews_at": sub.get("current_period_end"),
            "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
            "amount": sub.get("amount"),
            "currency": sub.get("currency"),
        }
    active = bool(rec.get("active"))
    return {
        "active": active,
        "status": "active" if active else "inactive",
        "interval": None,
        "renews_at": None,
        "cancel_at_period_end": False,
    }


@app.get("/api/me")
async def me(request: Request):
    email = session.read(request.cookies.get(session.COOKIE_NAME))
    if not email:
        return JSONResponse({"authenticated": False}, status_code=401)
    jobs = storage.jobs_for_email(email)
    recent = []
    for job in jobs[:8]:
        item = {
            "title": job.title,
            "author": job.author,
            "created_at": job.created_at,
            "word_count": job.word_count,
            "paid": job.paid,
        }
        if job.paid and job.download_token:
            item["downloads"] = {k: _download_url(job, k, job.download_token) for k in job.paid_outputs}
        recent.append(item)
    return {
        "authenticated": True,
        "email": email,
        "plan": _plan_status(storage.subscriber_record(email)),
        "books": {"count": len(jobs), "recent": recent},
        "capabilities": engine.capabilities(),
    }


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(session.COOKIE_NAME, path="/")
    return resp


def _event_email(data: dict) -> str | None:
    customer = data.get("customer") or {}
    return data.get("customer_email") or data.get("email") or customer.get("email")


async def _activate_subscription_for_job(data: dict) -> None:
    product_id = data.get("product_id") or (data.get("product") or {}).get("id")
    if product_id and product_id not in config.polar_product_ids():
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
            if s.get("product_id") in config.polar_product_ids()
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
