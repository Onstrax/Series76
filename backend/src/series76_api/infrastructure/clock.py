"""Clock abstraction for the Series 76 backend (Spec 3).

A small protocol so time-dependent logic (login lockout windows, token
expiry, job leases) can be driven by a fake clock in tests. Infrastructure,
because the real implementation reads the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """A source of the current UTC time."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class SystemClock:
    """Real clock reading the system wall clock in UTC."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""

        return datetime.now(UTC)


class FixedClock:
    """A controllable clock for tests; advances only when told to."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        self._now = start

    def now(self) -> datetime:
        """Return the current (frozen) time."""

        return self._now

    def advance(self, seconds: float) -> None:
        """Advance the clock by ``seconds``."""

        self._now = self._now + timedelta(seconds=seconds)


__all__ = ["Clock", "SystemClock", "FixedClock"]
