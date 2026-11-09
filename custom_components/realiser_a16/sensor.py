"""Sensors: what the A16 reports about presets, audio and firmware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .a16 import A16State
from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity


@dataclass(frozen=True, kw_only=True)
class A16SensorDescription(SensorEntityDescription):
    value: Callable[[A16State], str | int | None]


def _global(key: str, attr: str | None = None, **kwargs) -> A16SensorDescription:
    attr = attr or key
    return A16SensorDescription(
        key=key, translation_key=key, value=lambda s: getattr(s, attr), **kwargs
    )


def _user(user: str, attr: str, enabled: bool = True) -> A16SensorDescription:
    return A16SensorDescription(
        key=f"{attr}_{user}",
        translation_key=f"{attr}_{user}",
        value=lambda s: getattr(s.user(user), attr),
        entity_registry_enabled_default=enabled,
    )


def _firmware(key: str, fw_key: str, enabled: bool = True) -> A16SensorDescription:
    return A16SensorDescription(
        key=key,
        translation_key=key,
        value=lambda s: s.firmware.get(fw_key),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
    )


SENSORS: list[A16SensorDescription] = [
    _global("decoder"),
    _global("format"),
    _global("upmixer"),
    _global("legacy"),
    _global("user_mode"),
    _global("ht_mode"),
    _global("mode"),
    _global("menu_page", "page", entity_category=EntityCategory.DIAGNOSTIC),
    _firmware("firmware_a16", "A16FW"),
    _firmware("firmware_apm", "APMFW", False),
    _firmware("firmware_hsr", "HSRFW", False),
    _firmware("firmware_ht", "HTFW", False),
    _firmware("serial_number", "A16SN"),
]
for _u in ("a", "b"):
    SENSORS += [
        _user(_u, "name"),
        _user(_u, "room"),
        _user(_u, "layout"),
        _user(_u, "headphone"),
        _user(_u, "tri_level", False),
        _user(_u, "subject", False),
        _user(_u, "hpeq_file", False),
        _user(_u, "hpeq_subject", False),
        _user(_u, "hpeq_date", False),
        _user(_u, "hpeq_type", False),
    ]


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(A16Sensor(entry.runtime_data, desc) for desc in SENSORS)


class A16Sensor(A16Entity, SensorEntity):
    entity_description: A16SensorDescription

    def __init__(self, coordinator: A16Coordinator, description: A16SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        value = self.entity_description.value(self.a16)
        return None if value == "" else value
