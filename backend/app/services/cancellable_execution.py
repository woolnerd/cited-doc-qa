"""Helpers for running blocking demo work with cancellation support."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue as queue_module
from collections.abc import Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


def _process_worker(
    queue: mp.Queue[tuple[str, Any]],
    func: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """Execute a callable and send the result back through a queue."""
    try:
        queue.put(("ok", func(*args, **kwargs)))
    except Exception as exc:  # pragma: no cover - surfaced through parent process
        queue.put(("error", exc))


async def run_blocking_in_process(
    func: Callable[..., T],
    *args: Any,
    timeout_seconds: float,
    **kwargs: Any,
) -> T:
    """Run a blocking callable in a separate process and terminate it on cancel."""
    ctx = mp.get_context("spawn")
    queue: mp.Queue[tuple[str, Any]] = ctx.Queue()
    process = ctx.Process(
        target=_process_worker,
        args=(queue, func, args, kwargs),
        daemon=True,
    )
    process.start()
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    try:
        while process.is_alive():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                process.terminate()
                process.join(timeout=1)
                raise TimeoutError("Blocking demo work exceeded the configured timeout")

            await asyncio.sleep(min(0.1, remaining))

        process.join(timeout=1)
        try:
            status, payload = queue.get_nowait()
        except queue_module.Empty as exc:
            raise RuntimeError(
                "Blocking demo work exited without returning a result"
            ) from exc
        if status == "ok":
            return cast(T, payload)
        raise payload
    except asyncio.CancelledError:
        process.terminate()
        process.join(timeout=1)
        raise
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        queue.close()
        queue.join_thread()
