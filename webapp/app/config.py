"""Runtime configuration, all from environment variables (12-factor)."""

import os
from pathlib import Path

APP_NAME = "TalkToBook"
BASE_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = Path(os.environ.get("T2B_JOBS_DIR", BASE_DIR / "jobs"))

# Public origin used to build absolute URLs in checkout redirects / links.
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

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Pricing (cents). Back-compat: UNLOCK_PRICE_CENTS still works, but this is now
# the monthly creator plan price shown in the UI.
PLAN_PRICE_CENTS = int(
    os.environ.get("PLAN_PRICE_CENTS", os.environ.get("UNLOCK_PRICE_CENTS", "700"))
)
UNLOCK_PRICE_CENTS = PLAN_PRICE_CENTS
CURRENCY = os.environ.get("CURRENCY", "usd")

# Polar — when unset, the app runs in "intent capture" mode (no live payments),
# which is the PRD's "read demand before payments are wired" path.
POLAR_ACCESS_TOKEN = os.environ.get("POLAR_ACCESS_TOKEN", "").strip()
POLAR_PRODUCT_ID = os.environ.get("POLAR_PRODUCT_ID", "").strip()
POLAR_WEBHOOK_SECRET = os.environ.get("POLAR_WEBHOOK_SECRET", "").strip()
POLAR_SERVER = os.environ.get("POLAR_SERVER", "production").strip().lower()
POLAR_API_BASE = os.environ.get("POLAR_API_BASE", "").strip().rstrip("/")

# Chrome blocks downloads served over plain HTTP. In production, force HTTPS when
# PUBLIC_URL is HTTPS (Railway/custom domains) unless explicitly disabled.
FORCE_HTTPS = _env_bool(
    "FORCE_HTTPS",
    PUBLIC_URL.startswith("https://") and "localhost" not in PUBLIC_URL and "127.0.0.1" not in PUBLIC_URL,
)

# Dev escape hatch: unlock without paying (local demos only). Never set in prod.
ALLOW_FREE_UNLOCK = os.environ.get("ALLOW_FREE_UNLOCK", "").lower() in ("1", "true", "yes")

# Legal / contact (shown on the Terms page; set a real address before launch).
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@talktobook.example")
DMCA_EMAIL = os.environ.get("DMCA_EMAIL", "dmca@talktobook.example")

# Input guardrails.
MAX_TRANSCRIPT_CHARS = int(os.environ.get("MAX_TRANSCRIPT_CHARS", str(800_000)))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
ALLOWED_EXTS = {"txt", "md", "markdown", "srt", "vtt"}


def polar_api_base() -> str:
    if POLAR_API_BASE:
        return POLAR_API_BASE
    if POLAR_SERVER == "sandbox":
        return "https://sandbox-api.polar.sh/v1"
    return "https://api.polar.sh/v1"


def polar_enabled() -> bool:
    return bool(POLAR_ACCESS_TOKEN and POLAR_PRODUCT_ID)


def payments_enabled() -> bool:
    return polar_enabled()
