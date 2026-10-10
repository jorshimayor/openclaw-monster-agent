"""The notion worker must not spin on a failure that will never stop.

It did. `continue` on any failed get() meant a permanent error — the event
loop being closed at teardown — produced an infinite loop that logged a full
traceback every pass. That hung CI at the fifteen-minute job limit four times
before a faulthandler stack dump pointed here.
"""

import asyncio

import pytest

from src.knowledge import store as store_mod
from src.knowledge.store import _MAX_CONSECUTIVE_QUEUE_FAILURES


class _Queue:
    """A queue whose get() always fails, counting how often it is asked."""

    def __init__(self, exc: BaseException):
        self.exc = exc
        self.calls = 0

    def qsize(self) -> int:
        return 0

    async def get(self):
        self.calls += 1
        raise self.exc


def worker_with(queue):
    obj = object.__new__(store_mod.CrystallizedKnowledgeStore)
    obj._notion_queue = queue
    return obj


@pytest.mark.asyncio
async def test_a_closed_event_loop_stops_the_worker_rather_than_spinning():
    """The exact teardown failure: retrying cannot help, so it must not retry."""
    queue = _Queue(RuntimeError("Event loop is closed"))
    await asyncio.wait_for(worker_with(queue)._notion_worker(), timeout=5)
    assert queue.calls == 1, f"asked {queue.calls} times for a permanent failure"


@pytest.mark.asyncio
async def test_repeated_unknown_failures_give_up_instead_of_looping_forever():
    queue = _Queue(ValueError("something odd"))
    await asyncio.wait_for(worker_with(queue)._notion_worker(), timeout=5)
    assert queue.calls == _MAX_CONSECUTIVE_QUEUE_FAILURES


@pytest.mark.asyncio
async def test_cancellation_still_exits_cleanly():
    queue = _Queue(asyncio.CancelledError())
    await asyncio.wait_for(worker_with(queue)._notion_worker(), timeout=5)
    assert queue.calls == 1


@pytest.mark.asyncio
async def test_a_transient_failure_does_not_end_the_worker():
    """Giving up on the first blip would be the opposite mistake."""
    class _Flaky(_Queue):
        async def get(self):
            self.calls += 1
            if self.calls < 3:
                raise ValueError("transient")
            raise asyncio.CancelledError()

    queue = _Flaky(ValueError("unused"))
    await asyncio.wait_for(worker_with(queue)._notion_worker(), timeout=5)
    assert queue.calls == 3
