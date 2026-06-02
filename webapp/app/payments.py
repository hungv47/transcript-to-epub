"""Polar Checkout for the monthly creator plan.

When Polar isn't configured the app stays in intent-capture mode: unlock clicks
persist the email but do not charge. Live mode creates a hosted Polar checkout
session for the configured recurring product and fulfills clean editions when
the subscription is active.
"""

from __future__ import annotations

from email.utils import parseaddr

import requests

from . import config

try:
    from polar_sdk.webhooks import WebhookVerificationError, validate_event
except ImportError:  # keep local preview mode importable before deps install
    WebhookVerificationError = Exception
    validate_event = None


class PaymentError(RuntimeError):
    """Raised when a configured payment provider cannot create/verify checkout."""


def _compact(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in ("", None)}


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.POLAR_ACCESS_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def normalized_email(email: str) -> str:
    parsed = parseaddr(email or "")[1].strip().lower()
    return parsed


def _post_checkout(payload: dict) -> dict:
    """POST a checkout payload to Polar and return {"url", "checkout_id"}."""
    try:
        res = requests.post(
            f"{config.polar_api_base()}/checkouts",
            headers=_auth_headers(),
            json=payload,
            timeout=15,
        )
        res.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentError("Polar checkout is unavailable.") from exc
    checkout = res.json()
    if not checkout.get("url") or not checkout.get("id"):
        raise PaymentError("Polar returned an incomplete checkout session.")
    return {"url": checkout["url"], "checkout_id": checkout["id"]}


def create_checkout(job, email: str) -> dict:
    """Create a Polar Checkout session, or signal intent-capture mode.

    Returns either ``{"url": <checkout_url>, "checkout_id": ...}`` or
    ``{"intent": True}`` when Polar isn't configured.
    """
    if not config.polar_enabled():
        return {"intent": True}

    customer_email = normalized_email(email)
    payload = _compact({
        "products": config.polar_product_ids(),
        "customer_email": customer_email or None,
        "external_customer_id": customer_email or None,
        "metadata": _compact({
            "job_id": job.id,
            "email": customer_email,
        }),
        "allow_discount_codes": False,
        "success_url": f"{config.PUBLIC_URL}/success?job={job.id}&checkout_id={{CHECKOUT_ID}}",
        "return_url": f"{config.PUBLIC_URL}/?canceled={job.id}",
        "currency": config.CURRENCY.lower(),
    })
    return _post_checkout(payload)


def create_plan_checkout(interval: str, email: str = "") -> dict:
    """Create a Polar Checkout for the Creator Plan directly from pricing, with
    no preview job. The plan is email-linked: once active, generating and
    unlocking with the same email fulfills clean editions.

    Returns ``{"url", "checkout_id"}`` or ``{"intent": True}`` when Polar isn't
    configured. The selected interval picks a single product so the customer
    lands straight on that price.
    """
    if not config.polar_enabled():
        return {"intent": True}

    customer_email = normalized_email(email)
    payload = _compact({
        "products": [config.product_for_interval(interval)],
        "customer_email": customer_email or None,
        "external_customer_id": customer_email or None,
        "metadata": _compact({"plan_interval": interval, "email": customer_email}),
        "allow_discount_codes": False,
        "success_url": f"{config.PUBLIC_URL}/success?checkout_id={{CHECKOUT_ID}}",
        "return_url": f"{config.PUBLIC_URL}/?canceled=plan",
        "currency": config.CURRENCY.lower(),
    })
    return _post_checkout(payload)


def verify_webhook(payload: bytes, headers) -> dict | None:
    """Validate and parse a Polar webhook event."""
    if not config.POLAR_WEBHOOK_SECRET or validate_event is None:
        return None
    try:
        event = validate_event(
            body=payload,
            headers={k: v for k, v in headers.items()},
            secret=config.POLAR_WEBHOOK_SECRET,
        )
        if isinstance(event, dict):
            return event
        if hasattr(event, "model_dump"):
            return event.model_dump()
        if hasattr(event, "dict"):
            return event.dict()
        return {"type": getattr(event, "type", ""), "data": getattr(event, "data", {})}
    except WebhookVerificationError:
        return None
    except Exception:
        return None


def _checkout_valid(checkout: dict) -> bool:
    return (
        checkout.get("status") == "succeeded"
        and checkout.get("product_id") in config.polar_product_ids()
        and (checkout.get("currency") or "").lower() == config.CURRENCY.lower()
    )


def get_checkout(checkout_id: str) -> dict | None:
    if not config.polar_enabled():
        return None
    try:
        res = requests.get(
            f"{config.polar_api_base()}/checkouts/{checkout_id}",
            headers=_auth_headers(),
            timeout=15,
        )
        res.raise_for_status()
    except requests.RequestException:
        return None
    checkout = res.json()
    if not _checkout_valid(checkout):
        return None
    return checkout


def get_subscription(subscription_id: str) -> dict | None:
    """Fetch a subscription's live state from Polar (status, interval, period
    end, cancel flag). Returns None when payments are off or the call fails."""
    if not config.polar_enabled() or not subscription_id:
        return None
    try:
        res = requests.get(
            f"{config.polar_api_base()}/subscriptions/{subscription_id}",
            headers=_auth_headers(),
            timeout=15,
        )
        res.raise_for_status()
    except requests.RequestException:
        return None
    return res.json()


def checkout_job_id(checkout_id: str) -> str | None:
    """Return the job_id a succeeded Polar checkout belongs to, else None."""
    checkout = get_checkout(checkout_id)
    if not checkout:
        return None
    return (checkout.get("metadata") or {}).get("job_id")
