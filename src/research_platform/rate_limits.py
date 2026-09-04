from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse


class DomainLimiter:
    """Minimum spacing between requests to the same host.

    Two modes, because providers state their limits in two different ways. `wait()` spaces
    request *starts* and releases the host's lock before the caller goes out, so several
    requests can be in flight at once as long as they began far enough apart. `hold()` keeps
    the lock for the whole request, which is what a provider asking for a single connection
    actually means.
    """

    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        self.last_access: dict[str, float] = defaultdict(float)
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def _sleep_until_due(self, domain: str) -> None:
        wait_for = self.delay_s - (time.monotonic() - self.last_access[domain])
        if wait_for > 0:
            await asyncio.sleep(wait_for)

    async def wait(self, url: str) -> None:
        domain = urlparse(url).hostname or ""
        async with self.locks[domain]:
            await self._sleep_until_due(domain)
            self.last_access[domain] = time.monotonic()

    @asynccontextmanager
    async def hold(self, url: str) -> AsyncIterator[None]:
        """Hold the domain's slot for the whole request, then stamp the clock.

        The clock is stamped on exit rather than on entry so the interval is measured
        between the end of one request and the start of the next. A provider that caps
        concurrency to one connection is rate-limiting its own serving capacity, and
        measuring from the start would let a slow response shorten the real gap to nothing.
        """
        domain = urlparse(url).hostname or ""
        async with self.locks[domain]:
            await self._sleep_until_due(domain)
            try:
                yield
            finally:
                self.last_access[domain] = time.monotonic()


# Politeness is a property of the machine, not of a run. One limiter per AcquisitionService
# meant that with N runs in flight the same publisher was hit N times faster -- domain_delay_s
# silently became domain_delay_s / N. The reactive 429 backoff in the connectors is not a
# substitute: by the time it fires, the requests have already gone out.
_SHARED_LIMITERS: dict[float, DomainLimiter] = {}


def shared_domain_limiter(delay_s: float) -> DomainLimiter:
    """The process-wide limiter for this delay, created once."""
    limiter = _SHARED_LIMITERS.get(delay_s)
    if limiter is None:
        limiter = DomainLimiter(delay_s)
        _SHARED_LIMITERS[delay_s] = limiter
    return limiter
