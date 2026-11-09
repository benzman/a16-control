"""Switches: power, mute, test signal, head tracker and (optional) one per speaker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .a16 import SPEAKER_COMMAND_MAX, SPEAKERS, A16State
from .const import CONF_SPEAKER_SWITCHES
from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity


@dataclass(frozen=True, kw_only=True)
class A16SwitchDescription(SwitchEntityDescription):
    """A switch backed by a toggle key (or an on/off command pair)."""

    is_on: Callable[[A16State], bool | None]
    on_command: str
    off_command: str


SWITCHES = [
    A16SwitchDescription(
        key="power",
        translation_key="power",
        device_class=SwitchDeviceClass.SWITCH,
        is_on=lambda s: s.is_on if s.power is not None else None,
        on_command="power_on",
        off_command="power_standby",
    ),
    A16SwitchDescription(
        key="mute_a",
        translation_key="mute_a",
        is_on=lambda s: s.user_a.muted,
        on_command="mute_a",
        off_command="mute_a",
    ),
    A16SwitchDescription(
        key="mute_b",
        translation_key="mute_b",
        is_on=lambda s: s.user_b.muted,
        on_command="mute_b",
        off_command="mute_b",
    ),
    A16SwitchDescription(
        key="test",
        translation_key="test",
        is_on=lambda s: s.test,
        on_command="test",
        off_command="test",
    ),
    A16SwitchDescription(
        key="head_tracker",
        translation_key="head_tracker",
        is_on=lambda s: s.ht_active,
        on_command="ht",
        off_command="ht",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [A16Switch(coordinator, desc) for desc in SWITCHES]
    if entry.options.get(CONF_SPEAKER_SWITCHES):
        entities += [
            A16SpeakerSwitch(coordinator, speaker_id)
            for speaker_id in SPEAKERS
            if speaker_id <= SPEAKER_COMMAND_MAX
        ]
    async_add_entities(entities)


class A16Switch(A16Entity, SwitchEntity):
    """Most of these are toggle keys on the A16, so the command is only sent
    when the known state differs from the wanted one."""

    entity_description: A16SwitchDescription

    def __init__(self, coordinator: A16Coordinator, description: A16SwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on(self.a16)

    @property
    def assumed_state(self) -> bool:
        # Mute and head tracker state are only reported after their key was used.
        return self.is_on is None

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.is_on is not True:
            await self._do(self.client.send(self.entity_description.on_command))

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on is not False:
            await self._do(self.client.send(self.entity_description.off_command))


class A16SpeakerSwitch(A16Entity, SwitchEntity):
    """A virtual speaker. On = audible. Only available if the preset has it."""

    def __init__(self, coordinator: A16Coordinator, speaker_id: int) -> None:
        super().__init__(coordinator, f"speaker_{speaker_id}")
        self._speaker_id = speaker_id
        self._attr_translation_key = "speaker"
        self._attr_translation_placeholders = {"name": SPEAKERS[speaker_id][0]}

    @property
    def available(self) -> bool:
        return super().available and self._speaker_id in self.a16.visible_speakers

    @property
    def is_on(self) -> bool:
        return self._speaker_id in self.a16.active_speakers

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.is_on:
            await self._do(self.client.toggle_speaker(self._speaker_id))

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self._do(self.client.toggle_speaker(self._speaker_id))
