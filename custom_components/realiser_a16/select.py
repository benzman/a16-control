"""Select entities: source, presets, solo/mute mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .a16 import PRESET_COUNT, SOURCES
from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            A16SourceSelect(coordinator),
            A16PresetSelect(coordinator, "a"),
            A16PresetSelect(coordinator, "b"),
            A16SoloModeSelect(coordinator),
        ]
    )


class A16SourceSelect(A16Entity, SelectEntity):
    _attr_translation_key = "source"
    _attr_options = [label for _, label in SOURCES.values()]

    def __init__(self, coordinator: A16Coordinator) -> None:
        super().__init__(coordinator, "source")

    @property
    def current_option(self) -> str | None:
        return self.a16.source if self.a16.source in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self._do(self.client.select_source(option))


class A16PresetSelect(A16Entity, SelectEntity):
    _attr_options = [str(number) for number in range(1, PRESET_COUNT + 1)]

    def __init__(self, coordinator: A16Coordinator, user: str) -> None:
        super().__init__(coordinator, f"preset_{user}")
        self._user = user
        self._attr_translation_key = f"preset_{user}"

    @property
    def current_option(self) -> str | None:
        preset = self.a16.user(self._user).preset
        return str(preset) if preset else None

    async def async_select_option(self, option: str) -> None:
        await self._do(self.client.select_preset(self._user, int(option)))


class A16SoloModeSelect(A16Entity, SelectEntity):
    """What tapping a speaker does: solo it, or mute it (ALL key)."""

    _attr_translation_key = "solo_mode"
    _attr_options = ["solo", "mute"]

    def __init__(self, coordinator: A16Coordinator) -> None:
        super().__init__(coordinator, "solo_mode")

    @property
    def current_option(self) -> str | None:
        mode = (self.a16.solo_mode or "").lower()
        return mode if mode in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option != self.current_option:
            await self._do(self.client.send("all"))
