"""Client tests against the in-process A16 fake."""

from __future__ import annotations

import asyncio

import pytest
from a16 import (
    EVENT_CONNECTION,
    EVENT_LEVELS,
    EVENT_STATE,
    EVENT_TRACKER,
    A16Client,
    A16ConnectionError,
    async_fetch_info,
)

from tests.mock_a16 import MockA16

pytestmark = pytest.mark.usefixtures("fast_a16")


async def until(predicate, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.fixture
async def client(mock_a16: MockA16):
    client = A16Client("127.0.0.1", mock_a16.port, poll_interval=0.3)
    await client.start()
    assert await client.wait_connected(3)
    await until(lambda: client.state.firmware.get("A16SN") and client.state.visible_speakers)
    yield client
    await client.stop()


async def test_initial_refresh(client: A16Client):
    state = client.state
    assert state.power == "ON"
    assert state.source == "HDMI-1"
    assert state.user_a.volume == 65 and state.user_b.volume == 65
    assert state.visible_speakers == {1, 2, 3, 4, 5, 6, 25, 26, 47, 48}
    assert state.serial == "A16TEST#000001"


async def test_commands_update_state(client: A16Client, mock_a16: MockA16):
    events: list[str] = []
    client.add_listener(events.append)

    await client.select_source("HDMI-2")
    await until(lambda: client.state.source == "HDMI-2")
    await client.select_source("usb")
    await until(lambda: client.state.source == "USB")

    await client.set_mute("a", True)
    await until(lambda: client.state.user_a.muted is True)
    await client.set_mute("a", True)  # already muted: must not toggle back
    await asyncio.sleep(0.1)
    assert mock_a16.muted["A"] is True

    await client.power(False)
    await until(lambda: client.state.power == "STANDBY")
    assert EVENT_STATE in events


async def test_set_volume_steps_and_verifies(client: A16Client, mock_a16: MockA16):
    await client.set_volume("a", 70)
    assert mock_a16.volume["A"] == 70 and client.state.user_a.volume == 70
    await client.set_volume("b", 60)
    assert mock_a16.volume["B"] == 60
    await client.set_volume("a", 5)  # clamped
    assert mock_a16.volume["A"] == 27


async def test_preset_change_refreshes_layout(client: A16Client, mock_a16: MockA16):
    mock_a16.received.clear()
    await client.select_preset("a", 3)
    await until(lambda: client.state.user_a.preset == 3)
    await until(lambda: 0xAE in mock_a16.received and 0x37 in mock_a16.received)


async def test_speaker_toggle_in_mute_mode(client: A16Client, mock_a16: MockA16):
    await client.send("all")
    await until(lambda: client.state.solo_mode == "MUTE")
    await client.toggle_speaker(3)
    await until(lambda: 3 not in client.state.active_speakers)
    assert client.state.active_speakers == {1, 2, 4, 5, 6, 25, 26, 47, 48}
    await client.toggle_speaker(3)
    await until(lambda: 3 in client.state.active_speakers)


async def test_speaker_solo(client: A16Client):
    await client.toggle_speaker(25)
    await until(lambda: client.state.active_speakers == {25})
    assert client.state.all_active is False


async def test_ir_remote_push_is_picked_up(client: A16Client, mock_a16: MockA16):
    mock_a16.volume["A"] = 50  # someone used the IR remote
    await until(lambda: client.state.user_a.volume == 50)  # arrives with the broadcast
    mock_a16.volume["B"] = 40  # user B is not broadcast: found by the poll
    await until(lambda: client.state.user_b.volume == 40)


async def test_fast_poll_only_while_subscribed(client: A16Client, mock_a16: MockA16):
    events: list[str] = []
    client.add_listener(events.append)
    await asyncio.sleep(0.2)
    assert 0x6A not in mock_a16.received and 0x85 not in mock_a16.received

    stop_levels = client.subscribe_fast(EVENT_LEVELS)
    stop_tracker = client.subscribe_fast(EVENT_TRACKER)
    await until(lambda: EVENT_LEVELS in events and EVENT_TRACKER in events)
    assert client.state.levels["L5"] == 4
    assert client.state.user_a.ht_azimuth == -11

    stop_levels()
    stop_tracker()
    await asyncio.sleep(0.2)
    mock_a16.received.clear()
    await asyncio.sleep(0.3)
    assert 0x6A not in mock_a16.received and 0x85 not in mock_a16.received


async def test_reconnect(client: A16Client, mock_a16: MockA16):
    events: list[str] = []
    client.add_listener(events.append)
    mock_a16.drop_clients()
    await until(lambda: not client.connected)
    with pytest.raises(A16ConnectionError):
        await client.send("menu")
    await until(lambda: client.connected)
    assert mock_a16.connections == 2
    assert events.count(EVENT_CONNECTION) >= 2


async def test_dropped_commands_are_repeated(mock_a16: MockA16):
    """The real A16 drops commands that arrive while it is busy: no answer -> send again."""
    mock_a16.min_gap = 0.1  # with the test pacing (no gap) every second command is dropped
    client = A16Client("127.0.0.1", mock_a16.port)
    await client.start()
    try:
        assert await client.wait_connected(3)
        await until(lambda: client.state.firmware.get("A16SN"), timeout=6)
        await client.volume_step("a", True, 5)
        assert client.state.user_a.volume == 70 and mock_a16.volume["A"] == 70
        assert mock_a16.dropped and client.unanswered
    finally:
        await client.stop()


async def test_silent_connection_is_not_connected(mock_a16: MockA16):
    """The A16 can accept a connection without serving it: that is not 'connected'."""
    mock_a16.silent_connections = 2
    events: list[str] = []
    client = A16Client("127.0.0.1", mock_a16.port)
    client.add_listener(events.append)
    await client.start()
    try:
        await asyncio.sleep(0.3)
        assert not client.connected and EVENT_CONNECTION not in events
        with pytest.raises(A16ConnectionError):
            await client.send("menu")
        assert await client.wait_connected(5)
        assert mock_a16.connections == 3
        assert events.count(EVENT_CONNECTION) == 1
    finally:
        await client.stop()


async def test_reconnect_keeps_a_gap(mock_a16: MockA16, monkeypatch):
    """Reconnecting right after a disconnect locks a real A16 up."""
    import time  # noqa: PLC0415

    import a16.client as lib_client  # noqa: PLC0415

    monkeypatch.setattr(lib_client, "RECONNECT_GAP", 0.6)
    await async_fetch_info("127.0.0.1", mock_a16.port, timeout=2)
    closed = time.monotonic()
    client = A16Client("127.0.0.1", mock_a16.port)
    await client.start()
    try:
        assert await client.wait_connected(5)
        assert time.monotonic() - closed >= 0.6
    finally:
        await client.stop()


async def test_fetch_info(mock_a16: MockA16):
    state = await async_fetch_info("127.0.0.1", mock_a16.port, timeout=2)
    assert state.serial == "A16TEST#000001"
    assert state.power == "ON"


async def test_fetch_info_no_server():
    with pytest.raises(A16ConnectionError):
        await async_fetch_info("127.0.0.1", 1, timeout=1)
