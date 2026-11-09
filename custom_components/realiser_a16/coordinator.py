"""Push coordinator: forwards A16 state changes to the entities."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .a16 import EVENT_CONNECTION, EVENT_STATE, A16Client, A16State
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type A16ConfigEntry = ConfigEntry[A16Coordinator]


class A16Coordinator(DataUpdateCoordinator[A16State]):
    """The client pushes; nothing is polled from here."""

    config_entry: A16ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: A16ConfigEntry, client: A16Client) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.client = client
        self.data = client.state
        self._remove_listener: Callable[[], None] | None = client.add_listener(self._on_event)

    @callback
    def _on_event(self, kind: str) -> None:
        if kind in (EVENT_STATE, EVENT_CONNECTION):
            self.async_set_updated_data(self.client.state)

    async def async_shutdown(self) -> None:
        """Runs on unload; Home Assistant may call it more than once."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
            await self.client.stop()
        await super().async_shutdown()
