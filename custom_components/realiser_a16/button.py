"""Buttons for one-shot actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity

# key -> (command or None for a full refresh, entity category)
BUTTONS: dict[str, tuple[str | None, EntityCategory | None]] = {
    "headphone_mode": ("headphone", None),
    "speaker_mode": ("speaker", None),
    "reset_levels": ("reset_levels", EntityCategory.DIAGNOSTIC),
    "refresh": (None, EntityCategory.DIAGNOSTIC),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(A16Button(entry.runtime_data, key) for key in BUTTONS)


class A16Button(A16Entity, ButtonEntity):
    def __init__(self, coordinator: A16Coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._command, self._attr_entity_category = BUTTONS[key]
        self._attr_translation_key = key

    async def async_press(self) -> None:
        if self._command is None:
            await self._do(self.client.refresh(full=True))
        else:
            await self._do(self.client.send(self._command))
