"""Binary sensors: connection and tactile outputs."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            A16ConnectedSensor(coordinator),
            A16TactileSensor(coordinator, "a"),
            A16TactileSensor(coordinator, "b"),
        ]
    )


class A16ConnectedSensor(A16Entity, BinarySensorEntity):
    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: A16Coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.client.connected


class A16TactileSensor(A16Entity, BinarySensorEntity):
    def __init__(self, coordinator: A16Coordinator, user: str) -> None:
        super().__init__(coordinator, f"tactile_{user}")
        self._user = user
        self._attr_translation_key = f"tactile_{user}"

    @property
    def is_on(self) -> bool | None:
        return self.a16.user(self._user).tactile
