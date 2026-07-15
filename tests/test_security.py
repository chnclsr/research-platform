from __future__ import annotations

import socket

import pytest

from research_platform.acquisition import UnsafeUrlError, validate_public_url


@pytest.mark.asyncio
async def test_private_literal_is_blocked():
    with pytest.raises(UnsafeUrlError):
        await validate_public_url("http://127.0.0.1/secret")


@pytest.mark.asyncio
async def test_nonstandard_port_is_blocked():
    with pytest.raises(UnsafeUrlError):
        await validate_public_url("https://example.com:8443/data")


@pytest.mark.asyncio
async def test_dns_rebinding_target_is_blocked(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError):
        await validate_public_url("https://attacker.example/document")


@pytest.mark.asyncio
async def test_public_literal_is_allowed():
    await validate_public_url("https://1.1.1.1/")

