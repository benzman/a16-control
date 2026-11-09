"""Remote entity: every key of the A16 IR remote, plus all other commands by name."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import ATTR_DELAY_SECS, ATTR_NUM_REPEATS, RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .a16 import IR_KEYS
from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([A16Remote(entry.runtime_data)])


class A16Remote(A16Entity, RemoteEntity):
    """remote.send_command accepts key names (menu, enter, up, 1, cal ...),

    command names (source_hdmi1, preset_a_3, speaker_12, power_on ...) and raw
    codes (0x43).
    """

    _attr_name = None

    def __init__(self, coordinator: A16Coordinator) -> None:
        super().__init__(coordinator, "remote")

    @property
    def is_on(self) -> bool | None:
        return self.a16.is_on if self.a16.power is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "keys": list(IR_KEYS),
            "last_key": self.a16.last_key,
            "menu_page": self.a16.page,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._do(self.client.power(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._do(self.client.power(False))

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        repeats = kwargs.get(ATTR_NUM_REPEATS) or 1
        delay = kwargs.get(ATTR_DELAY_SECS) or 0
        commands = list(command)
        for index in range(repeats):
            if index and delay:
                await asyncio.sleep(delay)
            await self._do(self.client.send_many(commands))
