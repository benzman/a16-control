"""Asyncio client for the Realiser A16 IP command server.

One persistent TCP connection. The A16 pushes a user A status block about
once a second and answers every command with NUL/CR framed tokens; there is
no request/response correlation, so the client simply keeps a state object
up to date and tells listeners when it changed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Iterable

from . import parser as p
from .protocol_gen import (
    COMMANDS,
    DEFAULT_PORT,
    IR_KEYS,
    PRESET_A_BASE,
    PRESET_B_BASE,
    PRESET_COUNT,
    SOURCES,
    SPEAKER_BASE,
    SPEAKER_COMMAND_MAX,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .state import A16State

_LOGGER = logging.getLogger(__name__)

# Listener event kinds
EVENT_STATE = "state"
EVENT_LEVELS = "levels"
EVENT_TRACKER = "tracker"
EVENT_CONNECTION = "connection"

CONNECT_TIMEOUT = 10.0
RX_TIMEOUT = 30.0  # no data for this long -> reconnect
# The A16 handles one command at a time and silently drops what arrives while
# it is busy (measured on FW 2.17: queries 0.3 s apart lose a third). So only
# one command is in flight: wait for its answer, repeat it once if none comes.
SEND_GAP = 0.5  # minimum time between two commands, even when the answer came sooner
ACK_TIMEOUT = 2.0  # answers take 0.2-1.1 s
SEND_ATTEMPTS = 2
# The A16 serves a single connection and needs a moment to notice that it was
# closed. A connection opened too soon is accepted but never served, and it
# blocks the next one as well - reconnecting quickly locks the client out for
# good. So: keep a gap after every disconnect, treat a connection as up only
# once data arrived, and back off when it stays silent.
RECONNECT_GAP = 5.0  # minimum time between a disconnect and the next connect
FIRST_DATA_TIMEOUT = 8.0  # connected but silent for this long -> not being served
RECONNECT_MIN = 5.0
RECONNECT_MAX = 120.0

_last_disconnect: dict[tuple[str, int], float] = {}


async def _wait_reconnect_gap(host: str, port: int) -> None:
    last = _last_disconnect.get((host, port))
    if last is not None and (wait := RECONNECT_GAP - (time.monotonic() - last)) > 0:
        await asyncio.sleep(wait)


async def _close_writer(writer: asyncio.StreamWriter, host: str, port: int) -> None:
    writer.close()
    with contextlib.suppress(OSError, TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(writer.wait_closed(), 2)
    _last_disconnect[(host, port)] = time.monotonic()
FAST_POLL = 0.5  # level meter / head tracker refresh while subscribed
VOLUME_SETTLE = 0.8  # no volume answer for this long -> stepping has settled
LAYOUT_REFRESH_DELAY = 1.5  # a preset load takes a moment before data is valid

Listener = Callable[[str], None]


class A16Error(Exception):
    """Base error."""


class A16ConnectionError(A16Error):
    """Not connected or connection lost."""


def resolve_command(command: str | int) -> int:
    """Translate a command name or hex string into a command code.

    Accepted: IR key names ("menu"), command names ("power_on"),
    "source_<id>", "preset_a_<n>", "preset_b_<n>", "speaker_<id>",
    and raw hex codes ("0x43", "43" is NOT accepted to avoid clashing with digit keys).
    """
    if isinstance(command, int):
        code = command
    else:
        name = command.strip().lower()
        if name in IR_KEYS:
            return IR_KEYS[name]
        if name in COMMANDS:
            return COMMANDS[name]
        try:
            if name.startswith("0x"):
                code = int(name, 16)
            elif name.startswith("source_"):
                return SOURCES[name[7:]][0]
            elif name.startswith(("preset_a_", "preset_b_")):
                number = int(name[9:])
                if not 1 <= number <= PRESET_COUNT:
                    raise ValueError
                return (PRESET_A_BASE if name[7] == "a" else PRESET_B_BASE) + number - 1
            elif name.startswith("speaker_"):
                number = int(name[8:])
                if not 1 <= number <= SPEAKER_COMMAND_MAX:
                    raise ValueError
                return SPEAKER_BASE + number
            else:
                raise ValueError
        except (ValueError, KeyError):
            raise A16Error(f"Unknown A16 command: {command!r}") from None
    if not 0 <= code <= 0xFF:
        raise A16Error(f"Command code out of range: {command!r}")
    return code


class A16Client:
    """Keeps a connection to the A16 open and mirrors its state."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, *, poll_interval: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.state = A16State()
        self.connected = False

        self._parser = p.A16Parser(self.state)
        self._listeners: list[Listener] = []
        self._writer: asyncio.StreamWriter | None = None
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0
        self._last_user_a_block = 0.0
        self._task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._volume_tasks: dict[str, asyncio.Task] = {}
        self._layout_refresh: asyncio.Task | None = None
        self._fast_subs = {EVENT_LEVELS: 0, EVENT_TRACKER: 0}
        self._fast_task: asyncio.Task | None = None
        self._state_event = asyncio.Event()
        self._ack = asyncio.Event()
        self._ack_on_user_a = False
        self.unanswered = 0  # commands (incl. repeats) the A16 did not answer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the connection loop (returns immediately)."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="a16-connection")

    async def stop(self) -> None:
        """Close the connection and stop all background work."""
        tasks = [t for t in (self._task, self._fast_task, self._layout_refresh) if t]
        tasks += list(self._tasks) + list(self._volume_tasks.values())
        self._task = self._fast_task = self._layout_refresh = None
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._close()

    async def wait_connected(self, timeout: float) -> bool:
        """Wait until connected and the first status arrived."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.connected and self.state.power is not None:
                return True
            await asyncio.sleep(0.05)
        return False

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        """Register a callback(event_kind); returns an unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self, kind: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind)
            except Exception:
                _LOGGER.exception("A16 listener failed")

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        backoff = RECONNECT_MIN
        while True:
            await _wait_reconnect_gap(self.host, self.port)
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
                )
            except (OSError, TimeoutError) as err:
                _LOGGER.debug("A16 connect to %s:%s failed: %s", self.host, self.port, err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)
                continue

            self._writer = writer
            self._parser = p.A16Parser(self.state)
            poller: asyncio.Task | None = None
            try:
                # A TCP connect proves nothing: ask something and wait for data.
                await asyncio.sleep(SEND_GAP)
                writer.write(f"{COMMANDS['power_status']:02x}\r\n".encode("ascii"))
                await writer.drain()
                self._last_send = time.monotonic()
                data = await asyncio.wait_for(reader.read(4096), FIRST_DATA_TIMEOUT)
                while data:
                    if not self.connected:
                        self.connected = True
                        backoff = RECONNECT_MIN
                        _LOGGER.info("Connected to Realiser A16 at %s:%s", self.host, self.port)
                        self._notify(EVENT_CONNECTION)
                        poller = asyncio.create_task(self._poll_loop(), name="a16-poll")
                        self._update_fast_task()
                    self._handle(data)
                    data = await asyncio.wait_for(reader.read(4096), RX_TIMEOUT)
                _LOGGER.debug("A16 closed the connection")
            except (OSError, TimeoutError) as err:
                if self.connected:
                    _LOGGER.debug("A16 connection lost: %r", err)
                else:
                    _LOGGER.debug(
                        "A16 accepted the connection but sends nothing; next try in %.0f s", backoff
                    )
            finally:
                if poller:
                    poller.cancel()
                was_connected = self.connected
                await self._close()
                if was_connected:
                    self._notify(EVENT_CONNECTION)
            if not was_connected:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)

    async def _close(self) -> None:
        writer, self._writer = self._writer, None
        self.connected = False
        if writer is not None:
            await _close_writer(writer, self.host, self.port)

    def _handle(self, data: bytes) -> None:
        touched = self._parser.feed(data)
        if p.USER_A_BLOCK in touched:
            self._last_user_a_block = time.monotonic()
            if self._ack_on_user_a:
                self._ack.set()
        if p.RESPONSE in touched:
            self._ack.set()
        if p.NEED_SPEAKERS in touched:
            self._spawn(self._send_quiet("speaker_status"))
        if p.NEED_LAYOUT in touched:
            self._schedule_layout_refresh()
        if p.STATE in touched:
            self._state_event.set()
            self._notify(EVENT_STATE)
        if p.LEVELS in touched:
            self._notify(EVENT_LEVELS)
        if p.TRACKER in touched:
            self._notify(EVENT_TRACKER)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_quiet(self, *commands: str | int) -> None:
        """Send, ignoring a lost connection (the reconnect does a full refresh)."""
        with contextlib.suppress(A16ConnectionError):
            for command in commands:
                await self.send(command)

    async def _poll_loop(self) -> None:
        """Initial full refresh, then a slow keep-alive poll.

        User A is pushed by the A16 itself; power state and user B are not.
        """
        with contextlib.suppress(A16ConnectionError):
            await self.refresh(full=True)
            cycle = 0
            while True:
                await asyncio.sleep(self.poll_interval)
                cycle += 1
                await self.send("power_status")
                await self.send("user_b_info")
                if time.monotonic() - self._last_user_a_block > 5:
                    await self.send("user_a_info")  # slave response is switched off
                if cycle % 6 == 0:
                    await self.send("speaker_visibility")
                    await self.send("assignments")

    def _schedule_layout_refresh(self) -> None:
        if self._layout_refresh and not self._layout_refresh.done():
            self._layout_refresh.cancel()

        async def _later() -> None:
            await asyncio.sleep(LAYOUT_REFRESH_DELAY)
            await self._send_quiet(
                "user_a_info", "user_b_info", "speaker_visibility", "assignments"
            )

        self._layout_refresh = asyncio.create_task(_later())

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send(self, command: str | int, *, repeats: int = 1, delay: float = 0.0) -> None:
        """Send a command by name or code."""
        code = resolve_command(command)
        payload = f"{code:02x}\r\n".encode("ascii")
        for index in range(max(1, repeats)):
            if index and delay:
                await asyncio.sleep(delay)
            async with self._send_lock:
                writer = self._writer
                if writer is None:
                    raise A16ConnectionError("Not connected to the A16")
                await self._send_acked(writer, code, payload)

    async def _send_acked(self, writer: asyncio.StreamWriter, code: int, payload: bytes) -> None:
        """Write one command and wait for its answer (send lock is held)."""
        for attempt in range(SEND_ATTEMPTS):
            gap = SEND_GAP - (time.monotonic() - self._last_send)
            if gap > 0:
                await asyncio.sleep(gap)
            self._ack.clear()
            # the answer to "user A info" looks exactly like the periodic push
            self._ack_on_user_a = code == COMMANDS["user_a_info"]
            try:
                writer.write(payload)
                await writer.drain()
            except OSError as err:
                raise A16ConnectionError(str(err)) from err
            self._last_send = time.monotonic()
            try:
                await asyncio.wait_for(self._ack.wait(), ACK_TIMEOUT)
            except TimeoutError:
                _LOGGER.debug("No answer to %02x (attempt %d)", code, attempt + 1)
                self.unanswered += 1
            else:
                return
            if self._writer is not writer:
                raise A16ConnectionError("Connection lost while sending")

    async def send_many(self, commands: Iterable[str | int], *, delay: float = 0.0) -> None:
        for index, command in enumerate(commands):
            if index and delay:
                await asyncio.sleep(delay)
            await self.send(command)

    async def refresh(self, *, full: bool = False) -> None:
        """Query the current state."""
        commands = ["power_status", "user_a_info", "user_b_info", "speaker_visibility"]
        if full:
            commands += ["firmware", "assignments"]
        await self.send_many(commands)

    async def power(self, on: bool) -> None:
        await self.send("power_on" if on else "power_standby")

    async def select_source(self, source: str) -> None:
        """Select a source by id ("hdmi1") or by its IN= label ("HDMI-1")."""
        for source_id, (code, label) in SOURCES.items():
            if source in (source_id, label):
                await self.send(code)
                return
        raise A16Error(f"Unknown source: {source!r}")

    async def select_preset(self, user: str, preset: int) -> None:
        await self.send(f"preset_{user.lower()}_{preset}")

    async def toggle_speaker(self, speaker_id: int) -> None:
        """Solo (solo mode) or mute/unmute (mute mode) a speaker."""
        await self.send(f"speaker_{speaker_id}")

    async def volume_step(self, user: str, up: bool, steps: int = 1) -> None:
        key = f"vol_{user.lower()}_{'up' if up else 'down'}"
        await self.send(key, repeats=steps)

    async def set_mute(self, user: str, mute: bool) -> None:
        """Mute is a toggle on the A16; skip it when the state is already right."""
        if self.state.user(user).muted is not mute:
            await self.send(f"mute_{user.lower()}")

    def set_volume(self, user: str, target: int) -> asyncio.Task:
        """Step the volume towards `target`. A newer call replaces a running one."""
        user = user.lower()
        if (running := self._volume_tasks.get(user)) and not running.done():
            running.cancel()
        task = asyncio.create_task(self._set_volume(user, target))
        self._volume_tasks[user] = task
        return task

    async def _set_volume(self, user: str, target: int) -> None:
        try:
            await self._step_to_volume(user, max(VOLUME_MIN, min(VOLUME_MAX, int(target))))
        except A16ConnectionError as err:
            _LOGGER.warning("Setting A16 volume failed: %s", err)

    async def _step_to_volume(self, user: str, target: int) -> None:
        user_state = self.state.user(user)
        if user_state.volume is None:
            await self.send(f"user_{user}_volume")
            await self._wait_state(1.0)
        # The A16 has no absolute volume command: step and verify, a few rounds.
        for _ in range(4):
            current = user_state.volume
            if current is None or current == target:
                return
            await self.volume_step(user, target > current, abs(target - current))
            await self.send(f"user_{user}_volume")
            # Answers trickle in one per step: judge only once they stopped.
            while user_state.volume != target and await self._wait_state(VOLUME_SETTLE):
                pass

    async def _wait_state(self, timeout: float) -> bool:
        """Wait for the next state change; False if none came in time."""
        self._state_event.clear()
        try:
            await asyncio.wait_for(self._state_event.wait(), timeout)
        except TimeoutError:
            return False
        return True

    # ------------------------------------------------------------------
    # Level meters / head tracker (polled only while somebody watches)
    # ------------------------------------------------------------------

    def subscribe_fast(self, kind: str) -> Callable[[], None]:
        """Keep polling EVENT_LEVELS or EVENT_TRACKER until the returned function is called."""
        self._fast_subs[kind] += 1
        self._update_fast_task()
        done = False

        def _unsubscribe() -> None:
            nonlocal done
            if not done:
                done = True
                self._fast_subs[kind] -= 1

        return _unsubscribe

    def _update_fast_task(self) -> None:
        if any(self._fast_subs.values()) and (self._fast_task is None or self._fast_task.done()):
            self._fast_task = asyncio.create_task(self._fast_loop(), name="a16-fast-poll")

    async def _fast_loop(self) -> None:
        while any(self._fast_subs.values()):
            # user commands go first: skip a round while something is being sent
            if self.connected and self.state.is_on and not self._send_lock.locked():
                commands: list[str] = []
                if self._fast_subs[EVENT_LEVELS]:
                    commands.append("levels")
                if self._fast_subs[EVENT_TRACKER]:
                    commands.append("user_a_ht")
                    if self.state.user_mode != "SINGLE":
                        commands.append("user_b_ht")
                await self._send_quiet(*commands)
            await asyncio.sleep(FAST_POLL)


async def async_fetch_info(host: str, port: int = DEFAULT_PORT, timeout: float = 6.0) -> A16State:
    """Connect once, read power state and firmware info, disconnect.

    Raises A16ConnectionError when the A16 cannot be reached or does not answer.
    """
    await _wait_reconnect_gap(host, port)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, TimeoutError) as err:
        raise A16ConnectionError(f"Cannot connect to {host}:{port}: {err}") from err
    parser = p.A16Parser()
    deadline = time.monotonic() + timeout
    try:
        for name in ("power_status", "firmware"):
            await asyncio.sleep(SEND_GAP)
            writer.write(f"{COMMANDS[name]:02x}\r\n".encode("ascii"))
            await writer.drain()
        while parser.state.power is None or "A16SN" not in parser.state.firmware:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                data = await asyncio.wait_for(reader.read(4096), remaining)
            except TimeoutError:
                break
            if not data:
                break
            parser.feed(data)
    except OSError as err:
        raise A16ConnectionError(str(err)) from err
    finally:
        await _close_writer(writer, host, port)
    if parser.state.power is None and not parser.state.firmware:
        raise A16ConnectionError(f"No answer from {host}:{port}")
    return parser.state
