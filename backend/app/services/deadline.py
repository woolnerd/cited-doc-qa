"""Request deadline shared by blocking provider calls running in worker threads.

Threads started with ``asyncio.to_thread`` cannot be cancelled. When a request
times out, the worker keeps running unless it checks a deadline itself. Services
use this to stop retrying, cap per-call HTTP timeouts, and avoid sleeping past
the request budget.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class Deadline:
    """A point in monotonic time after which work should stop."""

    def __init__(
        self, expires_at: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.expires_at = expires_at
        self._clock = clock

    @classmethod
    def after(
        cls, seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> Deadline:
        """Create a deadline ``seconds`` from now."""
        return cls(clock() + seconds, clock)

    def remaining(self) -> float:
        """Seconds left before the deadline (never negative)."""
        return max(0.0, self.expires_at - self._clock())

    def expired(self) -> bool:
        """Whether the deadline has passed."""
        return self.remaining() <= 0.0

    def bound(self, timeout: float) -> float:
        """Cap a per-call timeout at the remaining budget."""
        return min(timeout, self.remaining())

    def allows(self, seconds: float) -> bool:
        """Whether waiting ``seconds`` would still finish before the deadline."""
        return seconds < self.remaining()

    @staticmethod
    def bound_or_default(deadline: Deadline | None, timeout: float) -> float:
        """Cap ``timeout`` by ``deadline`` when one is set."""
        return deadline.bound(timeout) if deadline is not None else timeout
