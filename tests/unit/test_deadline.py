"""Tests for the request deadline helper."""

import pytest
from app.services.deadline import Deadline


class FakeClock:
    """Manually advanced monotonic clock."""

    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_remaining_counts_down_and_never_goes_negative():
    clock = FakeClock()
    deadline = Deadline.after(5.0, clock=clock)

    assert deadline.remaining() == 5.0
    clock.now += 2.0
    assert deadline.remaining() == 3.0
    clock.now += 10.0
    assert deadline.remaining() == 0.0


def test_expired_once_time_runs_out():
    clock = FakeClock()
    deadline = Deadline.after(1.0, clock=clock)

    assert deadline.expired() is False
    clock.now += 1.0
    assert deadline.expired() is True


@pytest.mark.parametrize(
    ("elapsed", "default", "expected"),
    [
        (0.0, 30.0, 5.0),  # remaining budget is tighter than the default
        (0.0, 2.0, 2.0),  # default is tighter than the remaining budget
        (4.5, 30.0, 0.5),
    ],
)
def test_bound_caps_timeout_at_remaining_budget(elapsed, default, expected):
    clock = FakeClock()
    deadline = Deadline.after(5.0, clock=clock)
    clock.now += elapsed

    assert deadline.bound(default) == pytest.approx(expected)


def test_allows_sleep_only_within_budget():
    clock = FakeClock()
    deadline = Deadline.after(3.0, clock=clock)

    assert deadline.allows(2.0) is True
    assert deadline.allows(3.0) is False


def test_bound_with_no_deadline_returns_default():
    assert Deadline.bound_or_default(None, 30.0) == 30.0
