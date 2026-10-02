"""Shopper accounts, the admin sign-in, and the session tokens both get.

Passwords are stored as PBKDF2 hashes. A session is a signed token (who,
role, expiry), so nothing is kept per session and a restart signs nobody out.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from shop import db

SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
PBKDF2_ROUNDS = 200_000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Identity:
    id: str
    role: str
    """`shopper` or `admin`."""
    name: str
    email: Optional[str]

    def public(self) -> dict:
        return {"id": self.id, "role": self.role, "name": self.name, "email": self.email}


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def _admin() -> tuple:
    name = (os.environ.get("ADMIN_USERNAME") or "scraper_admin").strip().strip("'\"")
    password = (os.environ.get("ADMIN_PASSWORD") or "").strip().strip("'\"")
    return name, password or None


def register(name: str, email: str, password: str) -> Identity:
    name = " ".join(str(name or "").split())[:80]
    email = str(email or "").strip().lower()[:320]
    password = str(password or "")
    if not name:
        raise AuthError(400, "invalid", "Please enter your name.")
    if not _EMAIL.match(email):
        raise AuthError(400, "invalid", "Please enter a valid email address.")
    if len(password) < 8:
        raise AuthError(400, "invalid", "Choose a password of at least 8 characters.")
    salt = secrets.token_hex(16)
    user_id = "u" + secrets.token_hex(6)
    try:
        with db.write() as conn:
            conn.execute(
                "INSERT INTO users(id, email, name, password_hash, salt, created_at) VALUES(?,?,?,?,?,?)",
                (user_id, email, name, _hash(password, salt), salt, db.iso()),
            )
    except sqlite3.IntegrityError:
        raise AuthError(409, "email-taken", "An account with this email already exists. Sign in instead.") from None
    return Identity(user_id, "shopper", name, email)


def login(identifier: str, password: str) -> Identity:
    identifier = str(identifier or "").strip()
    password = str(password or "")
    admin_name, admin_password = _admin()
    if identifier == admin_name:
        if admin_password and hmac.compare_digest(admin_password.encode(), password.encode()):
            return Identity("admin", "admin", admin_name, None)
        raise AuthError(401, "invalid-credentials", "The username or password is wrong.")
    with db.read() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (identifier.lower(),)).fetchone()
    # The same work whether or not the account exists, so timing does not say which.
    salt = row["salt"] if row else "00" * 16
    given = _hash(password, salt)
    if not row or not hmac.compare_digest(given, row["password_hash"]):
        raise AuthError(401, "invalid-credentials", "The email or password is wrong.")
    return Identity(row["id"], "shopper", row["name"], row["email"])


def _secret() -> bytes:
    configured = (os.environ.get("SHOP_SESSION_SECRET") or "").strip()
    if configured:
        return configured.encode("utf-8")
    with db.read() as conn:
        stored = db.get_setting(conn, "session_secret")
    if stored:
        return stored.encode("utf-8")
    with db.write() as conn:
        stored = db.get_setting(conn, "session_secret")
        if not stored:
            stored = secrets.token_hex(32)
            db.set_setting(conn, "session_secret", stored)
    return stored.encode("utf-8")


def _sign(body: str) -> str:
    return hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def issue(identity: Identity, ttl_seconds: int = SESSION_TTL_SECONDS, now: Optional[int] = None) -> str:
    expires = (int(time.time()) if now is None else now) + ttl_seconds
    body = "v1.%s.%s.%d" % (identity.role, identity.id, expires)
    return body + "." + _sign(body)


def verify(token: Optional[str], now: Optional[int] = None) -> Optional[Identity]:
    """Who a session token belongs to, or None when it is missing, forged or expired."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 5 or parts[0] != "v1" or not parts[3].isdigit():
        return None
    body = ".".join(parts[:4])
    if not hmac.compare_digest(_sign(body), parts[4]):
        return None
    if int(parts[3]) < (int(time.time()) if now is None else now):
        return None
    role, user_id = parts[1], parts[2]
    if role == "admin":
        return Identity("admin", "admin", _admin()[0], None)
    with db.read() as conn:
        row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    return Identity(row["id"], "shopper", row["name"], row["email"]) if row else None
