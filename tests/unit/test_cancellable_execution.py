"""Tests for cancellable blocking execution helpers."""

import time

import pytest
from app.services.cancellable_execution import run_blocking_in_process


def _slow_function(delay: float) -> str:
    """Sleep long enough to trigger the timeout path."""
    time.sleep(delay)
    return "done"


@pytest.mark.asyncio
async def test_run_blocking_in_process_times_out_quickly():
    """Timed-out work should be terminated instead of running to completion."""
    start = time.perf_counter()

    with pytest.raises(TimeoutError):
        await run_blocking_in_process(_slow_function, 1.0, timeout_seconds=0.1)

    elapsed = time.perf_counter() - start
    assert elapsed < 0.8
