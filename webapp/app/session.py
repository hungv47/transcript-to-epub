"""Signed, stateless session for the post-purchase dashboard.

No accounts, no database: after a verified Polar checkout the server issues a
short signed token carrying the customer's email, and the dashboard trusts the
token's HMAC signature instead of a login. Tampering or expiry yields no
session. The signing key is config.SESSION_SECRET.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from . import config

COOKIE_NAME = "t2b_session"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    sig = hmac.new(
        config.SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return _b64e(sig)


def issue(email: str, ttl_days: int | None = None) -> str | None:
    """Mint a signed session token for an email, valid for ttl_days. Returns
    None when no real signing secret is configured, so the dashboard stays off
    rather than handing out cookies signed with the public dev default."""
    if not config.session_secret_configured():
        return None
    ttl = (config.SESSION_TTL_DAYS if ttl_days is None else ttl_days) * 86400
    body = {"email": (email or "").strip().lower(), "exp": int(time.time()) + ttl}
    payload = _b64e(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def read(token: str | None) -> str | None:
    """Return the email from a valid, unexpired token, else None. Always None
    when no real signing secret is configured, so a cookie forged with the
    public dev default can never authenticate."""
    if not config.session_secret_configured() or not token or "." not in token:
        return None
    payload, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        body = json.loads(_b64d(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(body.get("exp", 0)) < time.time():
        return None
    return body.get("email") or None


def max_age() -> int:
    return config.SESSION_TTL_DAYS * 86400
