"""Realiser A16 IP control library (pure asyncio, no Home Assistant imports)."""

from .client import (
    EVENT_CONNECTION,
    EVENT_LEVELS,
    EVENT_STATE,
    EVENT_TRACKER,
    A16Client,
    A16ConnectionError,
    A16Error,
    async_fetch_info,
    resolve_command,
)
from .parser import A16Parser
from .protocol_gen import (
    COMMANDS,
    DEFAULT_PORT,
    IR_KEYS,
    PRESET_COUNT,
    SOURCES,
    SPEAKER_COMMAND_MAX,
    SPEAKERS,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .state import A16State, UserState

__all__ = [
    "COMMANDS",
    "DEFAULT_PORT",
    "EVENT_CONNECTION",
    "EVENT_LEVELS",
    "EVENT_STATE",
    "EVENT_TRACKER",
    "IR_KEYS",
    "PRESET_COUNT",
    "SOURCES",
    "SPEAKERS",
    "SPEAKER_COMMAND_MAX",
    "VOLUME_MAX",
    "VOLUME_MIN",
    "A16Client",
    "A16ConnectionError",
    "A16Error",
    "A16Parser",
    "A16State",
    "UserState",
    "async_fetch_info",
    "resolve_command",
]
