"""Credentials of the server: hashed API keys, signed end-user tokens and admin sessions.

* API keys (``dpk_<id>_<secret>``) are for the backend of the app that embeds dpdpkit. Only their SHA-256 hash
  is configured or stored; the key itself is shown once, by :func:`generate_api_key`. The secret part is 256
  random bits, so a fast hash is enough.
* End-user tokens are minted by that backend for the widgets: HMAC-signed, short-lived, bound to one subject.
* Admin sessions are issued after a password or OIDC login. The password is kept as a salted scrypt hash.

Tokens are signed with ``Settings.signing_key``. Each token type uses its own derived key, so a token of one
type is never accepted as another.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass

API_KEY_PREFIX = "dpk_"
USER_TOKEN = "user"
ADMIN_TOKEN = "admin"
DEFAULT_USER_TTL = 900  # seconds
DEFAULT_ADMIN_TTL = 8 * 3600
_SCRYPT = (2**14, 8, 1)


class AuthError(Exception):
    """A credential is missing, malformed, expired or wrong."""


def generate_api_key() -> tuple[str, str]:
    """Return ``(key, hash)``. Show the key to its owner once; keep only the hash."""
    key = f"{API_KEY_PREFIX}{secrets.token_hex(4)}_{secrets.token_urlsafe(32)}"
    return key, hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key(key: str, hashes: Iterable[str]) -> bool:
    if not key.startswith(API_KEY_PREFIX):
        return False
    digest = hash_api_key(key)
    matched = False
    for stored in hashes:  # no early exit: the time taken does not reveal which hash matched
        matched |= hmac.compare_digest(digest, stored.lower())
    return matched


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    n, r, p = _SCRYPT
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(expected))
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, binascii.Error):
        return False


@dataclass(frozen=True)
class Claims:
    type: str
    subject: str
    expires_at: int
    scope: str = ""


def issue_token(
    signing_key: str, token_type: str, subject: str, *, ttl: int, scope: str = "", now: float | None = None
) -> str:
    if not subject:
        raise ValueError("a token needs a subject")
    expires_at = int((time.time() if now is None else now) + ttl)
    payload = {"typ": token_type, "sub": subject, "exp": expires_at, "scp": scope}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_b64(_sign(signing_key, token_type, body))}"


def verify_token(signing_key: str, token_type: str, token: str, *, now: float | None = None) -> Claims:
    try:
        body, signature = token.split(".")
        if not hmac.compare_digest(_unb64(signature), _sign(signing_key, token_type, body)):
            raise AuthError("invalid token signature")
        payload = json.loads(_unb64(body))
        claims = Claims(
            type=str(payload["typ"]),
            subject=str(payload["sub"]),
            expires_at=int(payload["exp"]),
            scope=str(payload["scp"]),
        )
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise AuthError("malformed token") from exc
    if claims.type != token_type:
        raise AuthError("wrong token type")
    if (time.time() if now is None else now) >= claims.expires_at:
        raise AuthError("token expired")
    return claims


def _sign(signing_key: str, token_type: str, body: str) -> bytes:
    derived = hmac.new(signing_key.encode("utf-8"), f"dpdpkit-token:{token_type}".encode(), hashlib.sha256).digest()
    return hmac.new(derived, body.encode("ascii"), hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
