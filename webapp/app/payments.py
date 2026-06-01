"""Stripe Checkout (one-time unlock) with a no-keys intent-capture fallback.

When STRIPE_SECRET_KEY is unset the app can't take live payments — the PRD's
explicit "read demand before payments are wired" phase. In that mode
``create_checkout`` returns an ``intent`` marker instead of a redirect URL, and
the caller records the email as a demand signal.
"""

from __future__ import annotations

from . import config

try:
    import stripe  # type: ignore
except ImportError:  # keep importable without the dependency
    stripe = None


def create_checkout(job, email: str) -> dict:
    """Create a one-time Checkout Session, or signal intent-capture mode.

    Returns either ``{"url": <checkout_url>, "session_id": ...}`` or
    ``{"intent": True}`` when Stripe isn't configured.
    """
    if not config.stripe_enabled() or stripe is None:
        return {"intent": True}

    stripe.api_key = config.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=email or None,
        line_items=[{
            "price_data": {
                "currency": config.CURRENCY,
                "unit_amount": config.UNLOCK_PRICE_CENTS,
                "product_data": {
                    "name": f"{config.APP_NAME} — unlock “{job.title}”",
                    "description": "Clean, branded edition · EPUB + PDF + Kindle, watermark removed.",
                },
            },
            "quantity": 1,
        }],
        metadata={"job_id": job.id},
        success_url=f"{config.PUBLIC_URL}/success?job={job.id}&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{config.PUBLIC_URL}/?canceled={job.id}",
    )
    return {"url": session.url, "session_id": session.id}


def verify_webhook(payload: bytes, sig_header: str):
    """Validate and parse a Stripe webhook event. Returns the event or None."""
    if stripe is None or not config.STRIPE_WEBHOOK_SECRET:
        return None
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):  # type: ignore[attr-defined]
        return None


def session_is_paid(session_id: str) -> bool:
    """Confirm a Checkout Session is paid (used by the success page poll)."""
    if not config.stripe_enabled() or stripe is None:
        return False
    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        s = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return False
    return s.get("payment_status") == "paid"
