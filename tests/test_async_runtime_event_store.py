"""Tests for AsyncRuntimeEventStore executor delegation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.autodoctor.runtime_event_store import AsyncRuntimeEventStore


@pytest.mark.asyncio
async def test_async_record_trigger_uses_executor() -> None:
    """Async wrapper should delegate record_trigger to hass executor."""
    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run)

    store = MagicMock()
    wrapper = AsyncRuntimeEventStore(hass, store)
    ts = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)

    await wrapper.async_record_trigger("automation.async", ts)

    hass.async_add_executor_job.assert_awaited_once_with(
        store.record_trigger,
        "automation.async",
        ts,
    )


@pytest.mark.asyncio
async def test_async_get_events_uses_executor_and_returns_result() -> None:
    """Async read APIs should execute on executor and return sync result."""
    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run)

    store = MagicMock()
    store.get_events.return_value = [1.0, 2.0]
    wrapper = AsyncRuntimeEventStore(hass, store)

    result = await wrapper.async_get_events("automation.async")

    hass.async_add_executor_job.assert_awaited_once_with(
        store.get_events,
        "automation.async",
        None,
        None,
    )
    assert result == [1.0, 2.0]


@pytest.mark.asyncio
async def test_async_record_trigger_drops_when_inflight_limit_reached() -> None:
    """Write saturation should drop new trigger writes instead of blocking forever."""
    hass = MagicMock()
    release_first = asyncio.Event()

    write_calls = 0

    async def _run(func, *args):
        nonlocal write_calls
        write_calls += 1
        if write_calls == 1:
            await release_first.wait()
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run)

    store = MagicMock()
    wrapper = AsyncRuntimeEventStore(hass, store, max_in_flight=1)
    ts = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)

    first = asyncio.create_task(wrapper.async_record_trigger("automation.a", ts))
    await asyncio.sleep(0)
    second = await asyncio.wait_for(
        wrapper.async_record_trigger("automation.b", ts),
        timeout=0.1,
    )
    release_first.set()
    first_result = await first

    assert first_result is True
    assert second is False
    assert wrapper.dropped_events == 1
    assert wrapper.pending_jobs == 0
