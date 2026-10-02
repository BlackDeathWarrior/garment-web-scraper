"""Small signed tokens: the admin's session, and a shopper's key to their own request.

Both are HMACs, so nothing is stored and a worker restart does not sign
anyone out.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

SESSION_TTL_SECONDS = 12 * 60 * 60


def _mac(secret: str, purpose: str, value: str) -> str:
    key = hashlib.sha256((purpose + ":" + secret).encode("utf-8")).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_session(secret: str, ttl_seconds: int = SESSION_TTL_SECONDS, now: Optional[int] = None) -> str:
    """The token /api/auth/login hands the admin. `secret` is the admin password."""
    expires = (int(time.time()) if now is None else now) + ttl_seconds
    return "v1.%d.%s" % (expires, _mac(secret, "session", str(expires)))


def verify_session(secret: Optional[str], token: Optional[str], now: Optional[int] = None) -> bool:
    if not secret or not token:
        return False
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1" or not parts[1].isdigit():
        return False
    if int(parts[1]) < (int(time.time()) if now is None else now):
        return False
    return hmac.compare_digest(_mac(secret, "session", parts[1]), parts[2])


def tracking_token(secret: Optional[str], reference: str) -> Optional[str]:
    """What a shopper needs, with the reference, to read their request back."""
    if not secret:
        return None
    return _mac(secret, "tracking", reference.upper())[:32]


def verify_tracking(secret: Optional[str], reference: str, token: Optional[str]) -> bool:
    expected = tracking_token(secret, reference)
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token.strip().lower())
