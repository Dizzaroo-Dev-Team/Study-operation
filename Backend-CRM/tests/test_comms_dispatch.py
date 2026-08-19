"""Job C STEP 5 — dispatch-layer repairs that are safe to ship.

Covers:
  * FF-1: COMMS_DISPATCH_FIX makes the enqueue a direct, synchronous `.delay()`
    (not GC-droppable); flag-OFF keeps the wrapped enqueue.
  * REDIS-NORECONNECT: COMMS_REALTIME_RESILIENT makes the listener reconnect on
    error; flag-OFF permanently disables (legacy).
  * TASK-ENGINE-DISPOSE: COMMS_REALTIME_RESILIENT skips per-task engine.dispose();
    flag-OFF disposes every task.

(The SMTP auto-retry and the stuck-QUEUED sweeper are NOT here — they are held
under STOP-RULE S3, see the Job C report.)

`asyncio_mode = auto`.
"""
import asyncio

import pytest



# --------------------------------------------------------------------------- #
# FF-1 — dispatch helper
# --------------------------------------------------------------------------- #

class _FakeTask:
    def __init__(self):
        self.calls = []

    def delay(self, *a, **k):
        self.calls.append((a, k))


async def test_ff1_enqueues_directly_and_synchronously(monkeypatch):
    import app.modules.communications.dispatch as dispatch
    fake = _FakeTask()
    monkeypatch.setattr("app.workers.tasks.send_message_task", fake)

    await dispatch.enqueue_send_message("msg-1")
    # Direct: .delay already called by the time the helper returns (not droppable).
    assert fake.calls == [(("msg-1",), {})]


async def test_ff1_ai_enqueues_directly(monkeypatch):
    import app.modules.communications.dispatch as dispatch
    fake = _FakeTask()
    monkeypatch.setattr("app.workers.tasks.process_message_ai_task", fake)

    await dispatch.enqueue_ai_message("msg-1", "conv-1", "hello")
    assert fake.calls == [(("msg-1", "conv-1", "hello"), {})]


# --------------------------------------------------------------------------- #
# REDIS-NORECONNECT — listener reconnect
# --------------------------------------------------------------------------- #


async def test_redis_listener_reconnects(monkeypatch):
    from app.websocket_manager import WebSocketManager
    mgr = WebSocketManager()
    mgr.pubsub = object()
    calls = {"n": 0}

    async def consume():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient listener error")
        # Second time: break out so the test terminates.
        raise asyncio.CancelledError()

    async def fake_init():
        mgr.pubsub = object()

    async def no_sleep(_):
        return

    monkeypatch.setattr(mgr, "_consume_pmessages", consume)
    monkeypatch.setattr(mgr, "init_redis", fake_init)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    with pytest.raises(asyncio.CancelledError):
        await mgr._redis_listener()

    # Reconnected after the first error (consume called again) and did NOT
    # permanently disable.
    assert calls["n"] == 2
    assert mgr.redis_disabled is False


# --------------------------------------------------------------------------- #
# TASK-ENGINE-DISPOSE — per-task pool dispose
# --------------------------------------------------------------------------- #

class _FakeEngine:
    def __init__(self):
        self.disposed = 0

    async def dispose(self):
        self.disposed += 1


def _run_async_with(monkeypatch):
    import app.workers.tasks as tasks_mod
    fake_engine = _FakeEngine()
    monkeypatch.setattr(tasks_mod, "engine", fake_engine, raising=False)

    asyncio.set_event_loop(None)  # force run_async to create a fresh loop

    async def _coro():
        return 7

    result = tasks_mod.run_async(_coro())
    return result, fake_engine


def test_run_async_skips_dispose(monkeypatch):
    result, fake_engine = _run_async_with(monkeypatch)
    assert result == 7
    assert fake_engine.disposed == 0  # pool reused (no per-task dispose)
