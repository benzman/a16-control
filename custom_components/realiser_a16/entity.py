"""Base entity for the Realiser A16."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .a16 import A16Client, A16Error, A16State
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import A16Coordinator


class A16Entity(CoordinatorEntity[A16Coordinator]):
    """Common device info, availability and error handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: A16Coordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=entry.title,
            sw_version=coordinator.data.firmware.get("A16FW"),
            serial_number=coordinator.data.serial,
        )

    @property
    def client(self) -> A16Client:
        return self.coordinator.client

    @property
    def a16(self) -> A16State:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        return self.client.connected

    async def _do(self, action: Awaitable[None]) -> None:
        """Run a client call, turning library errors into Home Assistant errors."""
        try:
            await action
        except A16Error as err:
            raise HomeAssistantError(str(err)) from err
