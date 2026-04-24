"""Web Push (VAPID) sender + key generator.

Keys are read from env (VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY, both
URL-safe base64 without padding). `python -m app.webpush_gen` prints a
fresh pair you can paste into .env.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def _b64_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def public_key_b64() -> Optional[str]:
    key = (os.environ.get("VAPID_PUBLIC_KEY") or "").strip()
    return key or None


def _private_key_b64() -> Optional[str]:
    key = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    return key or None


def _vapid_claims() -> dict:
    subject = os.environ.get("VAPID_SUBJECT") or "mailto:admin@example.com"
    return {"sub": subject}


def send(subscription_info: dict, payload: dict) -> bool:
    priv = _private_key_b64()
    if not priv:
        log.debug("webpush: VAPID_PRIVATE_KEY not set, skipping send")
        return False

    try:
        from pywebpush import WebPushException, webpush as _webpush
    except ImportError:
        log.error("pywebpush not installed — run pip install -r requirements.txt")
        return False

    try:
        _webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=priv,
            vapid_claims=_vapid_claims(),
            ttl=3600,
        )
        return True
    except Exception as exc:  # pywebpush raises a custom exception on 404/410
        msg = str(exc)
        log.warning("webpush send failed: %s", msg[:200])
        # 404/410 means the subscription is dead — signal caller to delete it
        if "410" in msg or "404" in msg or "Gone" in msg or "NotFound" in msg:
            raise SubscriptionGone()
        return False


class SubscriptionGone(Exception):
    """Raised when the push endpoint has been permanently revoked."""
    pass


def generate_keypair() -> tuple[str, str]:
    """Generate a new P-256 VAPID key pair (private, public) as base64url."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    key = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64_nopad(priv_bytes), _b64_nopad(pub)
