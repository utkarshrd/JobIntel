"""
JobIntel - Authentication primitives (standard library only).

* Passwords are stored as salted scrypt hashes ("scrypt$n$r$p$salt$hash"); plain passwords are never stored or logged.
* A session is a signed, expiring access token: base64url(JSON{sub, exp}) + "." + HMAC-SHA256 signature using
  SECRET_KEY. It is stateless (nothing stored server-side) and is sent as `Authorization: Bearer <token>`.
  Users never see it: the web UI keeps it in the browser after a normal email + password sign-in.
* Repeated failed sign-ins for the same email + client are throttled (in-memory, per process).
Endpoints that read or change one user's profile, interactions or recommendations require that user's token.
`REQUIRE_USER_TOKEN=false` disables the check (used by the general automated tests).
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Dict, List, Optional

from fastapi import Header, HTTPException, status

from backend.app.core.config import settings

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
MIN_PASSWORD_LENGTH = 8


# ----------------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Constant-time check; False for users without a password (legacy / passwordless records)."""
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(got, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------------- access tokens
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest())


def create_access_token(user_id: int, ttl_seconds: Optional[int] = None) -> str:
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 if ttl_seconds is None else ttl_seconds
    payload = _b64(json.dumps({"sub": int(user_id), "exp": int(time.time()) + ttl}, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}"


def decode_access_token(token: str) -> Optional[int]:
    """User id if the token is genuine and unexpired, else None."""
    try:
        payload, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        data = json.loads(_unb64(payload))
        return int(data["sub"]) if data["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None


def _bearer(authorization: Optional[str]) -> Optional[int]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return decode_access_token(authorization[7:].strip())


def _unauthorized(detail: str = "Please sign in to continue.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def current_user_id(authorization: Optional[str] = Header(None)) -> int:
    """Dependency: the signed-in user's id (always enforced; used by /auth/me and account actions)."""
    uid = _bearer(authorization)
    if uid is None:
        raise _unauthorized("Your session is missing or has expired. Please sign in again.")
    return uid


def check_user_token(user_id: int, authorization: Optional[str]) -> None:
    """Raise 401 unless the caller is signed in as `user_id` (no-op when REQUIRE_USER_TOKEN is false)."""
    if settings.REQUIRE_USER_TOKEN and _bearer(authorization) != int(user_id):
        raise _unauthorized("Your session is missing or has expired. Please sign in again.")


def user_access(user_id: int, authorization: Optional[str] = Header(None)) -> None:
    """Dependency for routes that carry `user_id` as a path or query parameter."""
    check_user_token(user_id, authorization)


# ----------------------------------------------------------------------------- login throttling
class LoginThrottle:
    """Blocks an (email, client) pair after MAX_FAILURES failures within WINDOW seconds."""
    MAX_FAILURES, WINDOW = 5, 15 * 60

    def __init__(self):
        self._fails: Dict[str, List[float]] = {}

    def _recent(self, key: str) -> List[float]:
        now = time.time()
        self._fails[key] = [t for t in self._fails.get(key, []) if now - t < self.WINDOW]
        return self._fails[key]

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.MAX_FAILURES

    def fail(self, key: str) -> None:
        self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


login_throttle = LoginThrottle()
