from __future__ import annotations

import socket

import pytest

from research_platform import acquisition
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


# --- resolver outages ---------------------------------------------------------------
# Run 01M2FGWHWKW1GCRXVWTC97B94H lost 100 of 258 candidates to "[Errno -2] Name or service
# not known" while the names were fine: Docker Desktop's forwarder had timed out.

_PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("151.101.131.42", 0))]


@pytest.fixture
def no_dns_wait(monkeypatch):
    monkeypatch.setattr(acquisition, "_DNS_RETRY_DELAYS_S", (0.0, 0.0))


def _resolver(monkeypatch, *answers):
    queue = list(answers)
    calls: list[str] = []

    def fake_getaddrinfo(host, *args, **kwargs):
        calls.append(host)
        answer = queue.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return calls


@pytest.mark.asyncio
async def test_a_resolver_outage_is_ridden_out(monkeypatch, no_dns_wait):
    calls = _resolver(
        monkeypatch,
        socket.gaierror(socket.EAI_NONAME, "Name or service not known"),
        socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution"),
        _PUBLIC,
    )

    assert await validate_public_url("https://arxiv.org/abs/1706.03762") == 2
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_an_outage_that_outlasts_the_retries_still_fails(monkeypatch, no_dns_wait):
    calls = _resolver(
        monkeypatch, *[socket.gaierror(socket.EAI_NONAME, "Name or service not known")] * 3
    )

    with pytest.raises(socket.gaierror):
        await validate_public_url("https://arxiv.org/abs/1706.03762")
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_a_resolver_error_that_is_not_an_outage_is_not_retried(monkeypatch, no_dns_wait):
    calls = _resolver(monkeypatch, socket.gaierror(-12345, "not a lookup miss"))

    with pytest.raises(socket.gaierror):
        await validate_public_url("https://arxiv.org/abs/1706.03762")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_an_answer_that_arrives_after_a_retry_is_still_checked(monkeypatch, no_dns_wait):
    _resolver(
        monkeypatch,
        socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution"),
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))],
    )

    with pytest.raises(UnsafeUrlError):
        await validate_public_url("https://attacker.example/document")

