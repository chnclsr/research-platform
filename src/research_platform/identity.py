"""Database-backed identity: turning a presented credential into a :class:`Principal`.

:mod:`auth` holds the pure primitives (hashing, signing, key shapes) and touches no
database. This module is where a credential meets the ``users`` table. Every resolver
here ends at the same place -- an active user row -- so a deactivated account loses
every surface at once rather than one at a time.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    AuthError,
    Principal,
    generate_api_key,
    hash_secret,
    normalize_email,
    split_api_key,
    verify_secret,
    verify_session,
)
from .db import ApiKeyRow, TelegramIdentityRow, UserRow
from .schemas import new_id


class IdentityError(RuntimeError):
    """Raised for identity operations a caller asked for that cannot be satisfied."""


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    password: str,
    role: str = "user",
) -> UserRow:
    """Create an account. Raises :class:`IdentityError` if the email is taken."""
    if role not in ("user", "admin"):
        raise IdentityError(f"Unknown role: {role}")
    if not password:
        raise IdentityError("Password must not be empty")
    normalized = normalize_email(email)
    existing = await session.scalar(select(UserRow).where(UserRow.email == normalized))
    if existing is not None:
        raise IdentityError(f"A user with email {normalized} already exists")
    row = UserRow(
        id=new_id(),
        email=normalized,
        display_name=display_name or normalized,
        password_hash=hash_secret(password),
        role=role,
        is_active=True,
        token_version=0,
    )
    session.add(row)
    await session.commit()
    return row


async def set_password(session: AsyncSession, user: UserRow, password: str) -> None:
    """Replace a password and invalidate outstanding sessions.

    The version bump is the point: a password change that left old cookies working
    would not actually lock anyone out.
    """
    if not password:
        raise IdentityError("Password must not be empty")
    user.password_hash = hash_secret(password)
    user.token_version += 1
    await session.commit()


async def get_user(session: AsyncSession, user_id: str) -> UserRow | None:
    return await session.get(UserRow, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> UserRow | None:
    return await session.scalar(select(UserRow).where(UserRow.email == normalize_email(email)))


async def authenticate(session: AsyncSession, email: str, password: str) -> UserRow | None:
    """Verify an email/password pair, returning the user row or None.

    A missing user still costs a hash verification. Returning early would make
    "no such account" measurably faster than "wrong password", which turns the login
    form into an account-enumeration oracle.
    """
    user = await get_user_by_email(session, email)
    stored = user.password_hash if user is not None else _DUMMY_HASH
    matched = verify_secret(password, stored)
    if user is None or not matched or not user.is_active:
        return None
    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    return user


def principal_for(user: UserRow) -> Principal:
    return Principal.user(user.id, user.role)


async def principal_from_session(
    session: AsyncSession, cookie: str, *, secret_key: str, max_age_seconds: int
) -> Principal:
    """Resolve a panel session cookie.

    The signature proves we issued it; this then confirms the account still exists,
    is active, and has not had its sessions revoked via ``token_version``.
    """
    user_id, token_version = verify_session(secret_key, cookie, max_age_seconds=max_age_seconds)
    user = await get_user(session, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise AuthError("Session no longer valid")
    return principal_for(user)


async def principal_from_api_key(session: AsyncSession, presented: str) -> Principal:
    """Resolve an ``rp_<prefix>.<secret>`` key to its owner."""
    prefix, secret = split_api_key(presented)
    row = await session.scalar(select(ApiKeyRow).where(ApiKeyRow.prefix == prefix))
    if row is None or row.revoked_at is not None:
        raise AuthError("Unknown or revoked API key")
    if not verify_secret(secret, row.secret_hash):
        raise AuthError("Invalid API key")
    user = await get_user(session, row.user_id)
    if user is None or not user.is_active:
        raise AuthError("API key belongs to an inactive account")
    row.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return principal_for(user)


async def principal_from_user_id(session: AsyncSession, user_id: str) -> Principal:
    """Resolve the user named in an ``X-Actor-User`` header.

    Only ever called after the *service* token has been verified. The header names who
    a trusted intermediary is acting for; it is not itself a credential.
    """
    user = await get_user(session, user_id)
    if user is None or not user.is_active:
        raise AuthError("Unknown or inactive actor")
    return principal_for(user)


async def issue_api_key(session: AsyncSession, *, user_id: str, name: str) -> tuple[str, ApiKeyRow]:
    """Mint a key for a user. The full key is returned once and never stored."""
    user = await get_user(session, user_id)
    if user is None or not user.is_active:
        raise IdentityError("Cannot issue a key for an unknown or inactive user")
    full_key, prefix, secret_hash = generate_api_key()
    row = ApiKeyRow(
        id=new_id(),
        user_id=user_id,
        name=name or "unnamed",
        prefix=prefix,
        secret_hash=secret_hash,
    )
    session.add(row)
    await session.commit()
    return full_key, row


async def list_api_keys(session: AsyncSession, user_id: str) -> list[ApiKeyRow]:
    rows = await session.scalars(
        select(ApiKeyRow)
        .where(ApiKeyRow.user_id == user_id, ApiKeyRow.revoked_at.is_(None))
        .order_by(ApiKeyRow.created_at.desc())
    )
    return list(rows)


async def revoke_api_key(session: AsyncSession, *, user_id: str, key_id: str) -> bool:
    """Revoke a key, scoped to its owner so one user cannot revoke another's."""
    row = await session.get(ApiKeyRow, key_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return True


# Codes are read off a screen and typed into a phone, so the alphabet drops the glyphs
# that get confused there: O/0, I/1/L. Six characters over this alphabet is ~1.07e9
# combinations, which with a five-minute window and single use is not worth guessing.
_LINK_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LINK_CODE_LENGTH = 6


def format_link_code(code: str) -> str:
    """Group the code for legibility: ``A3F9K2`` renders as ``A3F-9K2``."""
    half = len(code) // 2
    return f"{code[:half]}-{code[half:]}"


def normalize_link_code(presented: str) -> str:
    """Accept what people actually type: lowercase, spaces, the display hyphen."""
    return "".join(ch for ch in presented.upper() if ch in _LINK_CODE_ALPHABET)


async def issue_telegram_link_code(
    session: AsyncSession, *, user_id: str, ttl_seconds: int
) -> str:
    """Issue a one-time code binding a Telegram account to this user.

    Stored hashed, like any other credential: the panel shows it once and the database
    never holds a value that would let someone else claim the account.
    """
    user = await get_user(session, user_id)
    if user is None or not user.is_active:
        raise IdentityError("Cannot issue a link code for an unknown or inactive user")
    code = "".join(secrets.choice(_LINK_CODE_ALPHABET) for _ in range(_LINK_CODE_LENGTH))
    user.telegram_link_code_hash = hash_secret(code)
    user.telegram_link_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    await session.commit()
    return code


async def consume_telegram_link_code(
    session: AsyncSession, *, code: str, telegram_user_id: int
) -> UserRow | None:
    """Redeem a link code, binding ``telegram_user_id`` to its issuer.

    Returns None for an unknown, expired or already-used code -- the bot cannot tell
    those apart, so a wrong guess reveals nothing about which codes are outstanding.
    """
    normalized = normalize_link_code(code)
    if len(normalized) != _LINK_CODE_LENGTH:
        return None
    now = datetime.now(timezone.utc)
    candidates = await session.scalars(
        select(UserRow).where(
            UserRow.telegram_link_code_hash.is_not(None),
            UserRow.is_active.is_(True),
        )
    )
    for user in candidates:
        expires_at = user.telegram_link_expires_at
        # Rows written before timezone-aware storage, and SQLite, can hand back naive
        # datetimes; compare on a common footing rather than raising.
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at < now:
            continue
        if not verify_secret(normalized, user.telegram_link_code_hash or ""):
            continue
        await link_telegram(session, telegram_user_id=telegram_user_id, user_id=user.id)
        # Clearing the code is what makes it single use. A leaked code would otherwise
        # let someone bind their own Telegram account to this user until it expired.
        user.telegram_link_code_hash = None
        user.telegram_link_expires_at = None
        await session.commit()
        return user
    return None


async def unlink_telegram(session: AsyncSession, *, user_id: str) -> bool:
    """Drop every Telegram binding for a user."""
    rows = list(
        await session.scalars(
            select(TelegramIdentityRow).where(TelegramIdentityRow.user_id == user_id)
        )
    )
    for row in rows:
        await session.delete(row)
    await session.commit()
    return bool(rows)


async def telegram_ids_for(session: AsyncSession, user_id: str) -> list[int]:
    rows = await session.scalars(
        select(TelegramIdentityRow.telegram_user_id).where(TelegramIdentityRow.user_id == user_id)
    )
    return list(rows)


async def link_telegram(session: AsyncSession, *, telegram_user_id: int, user_id: str) -> None:
    """Bind a Telegram account to a platform user, replacing any previous binding."""
    user = await get_user(session, user_id)
    if user is None or not user.is_active:
        raise IdentityError("Cannot link Telegram to an unknown or inactive user")
    row = await session.get(TelegramIdentityRow, telegram_user_id)
    if row is None:
        session.add(TelegramIdentityRow(telegram_user_id=telegram_user_id, user_id=user_id))
    else:
        row.user_id = user_id
        row.linked_at = datetime.now(timezone.utc)
    await session.commit()


async def principal_from_telegram(session: AsyncSession, telegram_user_id: int) -> Principal | None:
    """Resolve a Telegram sender, or None when that account has not been linked."""
    row = await session.get(TelegramIdentityRow, telegram_user_id)
    if row is None:
        return None
    user = await get_user(session, row.user_id)
    if user is None or not user.is_active:
        return None
    return principal_for(user)


# A well-formed hash of a value nobody holds, so that authenticating a nonexistent
# account performs the same work as authenticating a real one.
_DUMMY_HASH = hash_secret("dummy-password-for-constant-time-authentication")
