"""Session handling and capability checks for the control panel.

The panel used to protect itself with a single process-lifetime token embedded in the
page: anyone who could load ``/`` received full control, including the buttons that
start and stop containers. This module replaces that with per-user sessions and splits
the panel's capabilities in two -- the research data a user owns, and the operations
that affect the whole installation.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from hashlib import sha256

from fastapi import Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .auth import AuthError, Principal, sign_session
from .config import Settings, get_settings
from .db import SessionLocal
from .identity import principal_from_session

SESSION_COOKIE = "rp_session"
CSRF_HEADER = "X-Control-Token"

# Authentication decisions go to the panel's own log, which is administrator-only.
# They are not written to the events table: that is keyed by run_id, and a sign-in
# belongs to no run.
audit = logging.getLogger("research_platform.audit")

# Login throttling is deliberately in-process and per-address: the panel is a single
# uvicorn worker, and a shared store would be infrastructure this deployment does not
# otherwise need. It slows credential stuffing; it is not a defence against a botnet.


@dataclass
class _AttemptRecord:
    failures: int = 0
    first_failure: float = field(default_factory=time.time)


_login_attempts: dict[str, _AttemptRecord] = {}


def session_secret(settings: Settings | None = None) -> str:
    """The key that signs session cookies.

    Falls back to a per-process random value so a workstation install needs no setup;
    the cost is that everyone is logged out when the panel restarts. A shared
    deployment sets ``SESSION_SECRET`` and keeps its sessions across restarts.
    """
    settings = settings or get_settings()
    if settings.session_secret:
        return settings.session_secret
    return _ephemeral_secret()


_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


def _ephemeral_secret() -> str:
    return _EPHEMERAL_SECRET


def csrf_token(principal: Principal, settings: Settings | None = None) -> str:
    """A CSRF token bound to the signed-in user.

    Derived rather than stored, so it survives a restart exactly as long as the
    sessions it protects do, and it cannot be replayed under a different account.
    """
    settings = settings or get_settings()
    message = f"csrf:{principal.user_id}:{principal.role}".encode()
    return hmac.new(session_secret(settings).encode("utf-8"), message, sha256).hexdigest()


def issue_session_cookie(response: Response, user_id: str, token_version: int) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(session_secret(settings), user_id, token_version),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        # Only meaningful behind TLS; setting it on a plain-HTTP workstation install
        # would make the cookie silently unusable.
        secure=settings.control_panel_https,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


async def optional_principal(
    rp_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Principal | None:
    """Resolve the session cookie, or None when there is no valid session."""
    if not rp_session:
        return None
    settings = get_settings()
    async with SessionLocal() as session:
        try:
            return await principal_from_session(
                session,
                rp_session,
                secret_key=session_secret(settings),
                max_age_seconds=settings.session_max_age_seconds,
            )
        except AuthError:
            return None


async def require_user(
    principal: Principal | None = Depends(optional_principal),
) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor")
    return principal


async def require_admin(principal: Principal = Depends(require_user)) -> Principal:
    """Guards installation-wide operations: container control, logs, connector tests.

    Without this split, signing in would hand every user the button that stops the
    worker and the log stream that shows other people's runs.
    """
    if not principal.is_admin:
        audit.warning("admin action denied for user=%s role=%s", principal.user_id, principal.role)
        raise HTTPException(status_code=403, detail="Bu işlem yönetici yetkisi gerektirir")
    return principal


async def require_csrf(
    principal: Principal = Depends(require_user),
    x_control_token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> Principal:
    """State-changing panel calls must echo the token issued to this session."""
    expected = csrf_token(principal)
    if not x_control_token or not secrets.compare_digest(x_control_token, expected):
        raise HTTPException(status_code=403, detail="Geçersiz kontrol jetonu")
    return principal


async def require_admin_csrf(principal: Principal = Depends(require_csrf)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem yönetici yetkisi gerektirir")
    return principal


def login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def throttled(key: str) -> int:
    """Seconds the caller must wait, or 0 when they may try again now."""
    settings = get_settings()
    record = _login_attempts.get(key)
    if record is None or record.failures < settings.login_max_attempts:
        return 0
    elapsed = time.time() - record.first_failure
    if elapsed >= settings.login_lockout_seconds:
        _login_attempts.pop(key, None)
        return 0
    return int(settings.login_lockout_seconds - elapsed)


def record_failure(key: str, email: str = "") -> None:
    settings = get_settings()
    audit.warning("login failed from=%s email=%s", key, email[:120])
    record = _login_attempts.get(key)
    if record is None or time.time() - record.first_failure >= settings.login_lockout_seconds:
        _login_attempts[key] = _AttemptRecord(failures=1)
        return
    record.failures += 1
    if record.failures >= settings.login_max_attempts:
        audit.warning("login lockout from=%s after %s failures", key, record.failures)


def record_success(key: str, user_id: str = "") -> None:
    audit.info("login ok from=%s user=%s", key, user_id)
    _login_attempts.pop(key, None)
