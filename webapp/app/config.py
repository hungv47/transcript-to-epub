"""Runtime configuration, all from environment variables (12-factor)."""

import os
from pathlib import Path

APP_NAME = "TalkToBook"
BASE_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = Path(os.environ.get("T2B_JOBS_DIR", BASE_DIR / "jobs"))

# Public origin used to build absolute URLs in Stripe redirects / links.
# Explicit PUBLIC_URL wins; on Railway, fall back to the injected public domain
# so no manual post-deploy step is needed; else localhost for dev.
def _default_public_url() -> str:
    explicit = os.environ.get("PUBLIC_URL")
    if explicit:
        return explicit
    railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway:
        return f"https://{railway}"
    return "http://localhost:8000"


PUBLIC_URL = _default_public_url().rstrip("/")

# Pricing (cents). Validate at the low anchor per the PRD.
UNLOCK_PRICE_CENTS = int(os.environ.get("UNLOCK_PRICE_CENTS", "900"))
CURRENCY = os.environ.get("CURRENCY", "usd")

# Stripe — when unset, the app runs in "intent capture" mode (no live payments),
# which is the PRD's "read demand before payments are wired" path.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()

# Dev escape hatch: unlock without paying (local demos only). Never set in prod.
ALLOW_FREE_UNLOCK = os.environ.get("ALLOW_FREE_UNLOCK", "").lower() in ("1", "true", "yes")

# Legal / contact (shown on the Terms page; set a real address before launch).
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@talktobook.example")
DMCA_EMAIL = os.environ.get("DMCA_EMAIL", "dmca@talktobook.example")

# Input guardrails.
MAX_TRANSCRIPT_CHARS = int(os.environ.get("MAX_TRANSCRIPT_CHARS", str(800_000)))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
ALLOWED_EXTS = {"txt", "md", "markdown", "srt", "vtt"}


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)
