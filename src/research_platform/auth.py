"""Identity primitives shared by every surface that can reach research data.

The platform has three ways to present a credential -- a panel session cookie, a
per-user API key, and a service token acting on a user's behalf -- but only one way
to *be* someone: a :class:`Principal`. Everything downstream (the repository guard,
the panel's capability split, the API's route dependencies) reasons about principals
only, so a new credential type needs a resolver here and nothing else.

Password and API-key hashing use stdlib ``hashlib.scrypt``. That keeps the dependency
list unchanged -- notable because the control panel runs natively on Windows out of a
``.venv`` while the services run in containers, so a wheel-less build dependency would
break exactly one of the two. Moving to argon2 later means replacing
:func:`hash_secret` and :func:`verify_secret`; the stored format is self-describing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Literal

# scrypt parameters. n=2**14 with r=8 keeps a single verification near 60-90 ms on the
# machines this runs on, which is the usual trade-off point: slow enough to make offline
# cracking expensive, fast enough that a login does not feel stalled.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16

Role = Literal["user", "admin", "system"]

# API keys are presented as ``rp_<prefix>.<secret>``. The prefix is stored in the clear
# and indexed so a lookup is a single indexed query rather than a scan that verifies
# every row's hash. Only the secret half is hashed.
API_KEY_SCHEME = "rp"
_PREFIX_BYTES = 6
_SECRET_BYTES = 24


class AuthError(RuntimeError):
    """A credential was malformed, expired, or did not verify."""


@dataclass(frozen=True)
class Principal:
    """Who is asking. ``user_id`` is None only for the system principal."""

    user_id: str | None
    role: Role

    @property
    def is_admin(self) -> bool:
        """Admins and the system principal see every run."""
        return self.role in ("admin", "system")

    @property
    def is_system(self) -> bool:
        return self.role == "system"

    @classmethod
    def system(cls) -> Principal:
        """For the worker, pipeline and cron jobs -- code paths with no network caller.

        Never construct this from a request. It bypasses ownership filtering entirely.
        """
        return cls(user_id=None, role="system")

    @classmethod
    def user(cls, user_id: str, role: str = "user") -> Principal:
        if role not in ("user", "admin"):
            raise ValueError(f"Unknown role: {role}")
        return cls(user_id=user_id, role=role)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- hashing


def hash_secret(secret: str) -> str:
    """Hash a password or API key secret into a self-describing string.

    Format: ``scrypt$n$r$p$salt_b64$hash_b64``. Carrying the parameters in the record
    means raising the work factor later does not invalidate existing hashes -- they
    keep verifying under their original parameters until the owner next sets one.
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_scrypt_maxmem(_SCRYPT_N, _SCRYPT_R, _SCRYPT_P),
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64encode(salt),
            _b64encode(derived),
        ]
    )


def verify_secret(secret: str, stored: str) -> bool:
    """Constant-time check of a secret against a stored hash.

    Returns False rather than raising on a malformed record: a corrupt row must read
    as "wrong password", never as a crash that a caller might mistake for success.
    """
    try:
        scheme, n_raw, r_raw, p_raw, salt_b64, hash_b64 = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if scheme != "scrypt":
        return False
    try:
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    try:
        derived = hashlib.scrypt(
            secret.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=_scrypt_maxmem(n, r, p),
        )
    except ValueError:
        return False
    return hmac.compare_digest(derived, expected)


def _scrypt_maxmem(n: int, r: int, p: int) -> int:
    """Memory ceiling for scrypt, with headroom.

    CPython's default ``maxmem`` of 0 maps to OpenSSL's 32 MiB limit, which n=2**14
    with r=8 exceeds. Compute the real requirement (128 * n * r) and pad it rather
    than hardcoding a number that a future parameter bump would silently break.
    """
    return 128 * n * r * p + (1 << 20)


# ------------------------------------------------------------------------- API keys


def generate_api_key() -> tuple[str, str, str]:
    """Mint an API key.

    Returns ``(full_key, prefix, secret_hash)``. The full key is shown to the user
    exactly once; only prefix and hash are persisted.
    """
    prefix = secrets.token_urlsafe(_PREFIX_BYTES)[:8]
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return f"{API_KEY_SCHEME}_{prefix}.{secret}", prefix, hash_secret(secret)


def split_api_key(presented: str) -> tuple[str, str]:
    """Split ``rp_<prefix>.<secret>`` into its parts.

    Raises :class:`AuthError` on anything that is not shaped like one of our keys, so
    a caller cannot accidentally look up a row with attacker-chosen garbage.
    """
    if not presented.startswith(f"{API_KEY_SCHEME}_"):
        raise AuthError("Not an API key")
    body = presented[len(API_KEY_SCHEME) + 1 :]
    prefix, separator, secret = body.partition(".")
    if not separator or not prefix or not secret:
        raise AuthError("Malformed API key")
    return prefix, secret


# ------------------------------------------------------------------- session cookies


def sign_session(
    secret_key: str, user_id: str, token_version: int, *, issued_at: int | None = None
) -> str:
    """Produce a signed session cookie value.

    Carries ``token_version`` so bumping a user's version invalidates every cookie
    they hold -- the revocation path for a stolen laptop, without a session table.
    """
    payload = {
        "sub": user_id,
        "tv": token_version,
        "iat": int(time.time()) if issued_at is None else issued_at,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(secret_key, body)}"


def verify_session(secret_key: str, cookie: str, *, max_age_seconds: int) -> tuple[str, int]:
    """Verify a session cookie and return ``(user_id, token_version)``.

    Signature is checked before the payload is parsed, and expiry before the caller
    ever sees a user id. The caller must still confirm ``token_version`` and
    ``is_active`` against the database -- this function proves only that the cookie
    was issued by us and has not expired.
    """
    body, separator, signature = cookie.partition(".")
    if not separator:
        raise AuthError("Malformed session cookie")
    if not hmac.compare_digest(signature, _sign(secret_key, body)):
        raise AuthError("Bad session signature")
    try:
        payload = json.loads(_b64decode(body))
        user_id = str(payload["sub"])
        token_version = int(payload["tv"])
        issued_at = int(payload["iat"])
    except (ValueError, TypeError, KeyError):
        raise AuthError("Malformed session payload") from None
    if time.time() - issued_at > max_age_seconds:
        raise AuthError("Session expired")
    return user_id, token_version


def _sign(secret_key: str, body: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


# ---------------------------------------------------------------------------- base64


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding -- cookie- and header-safe."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def normalize_email(email: str) -> str:
    """Lowercase and trim so that lookups and the unique constraint agree."""
    return email.strip().lower()
