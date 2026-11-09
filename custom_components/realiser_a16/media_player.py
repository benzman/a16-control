"""Media players for user A and user B."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .a16 import PRESET_COUNT, SOURCES, VOLUME_MAX, VOLUME_MIN, UserState
from .coordinator import A16ConfigEntry, A16Coordinator
from .entity import A16Entity

PRESETS = [f"Preset {number}" for number in range(1, PRESET_COUNT + 1)]


async def async_setup_entry(
    hass: HomeAssistant, entry: A16ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(A16MediaPlayer(entry.runtime_data, user) for user in ("a", "b"))


class A16MediaPlayer(A16Entity, MediaPlayerEntity):
    """One listener (user A or B): volume, mute, preset; source and power are shared."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )
    _attr_source_list = [label for _, label in SOURCES.values()]
    _attr_sound_mode_list = PRESETS

    def __init__(self, coordinator: A16Coordinator, user: str) -> None:
        super().__init__(coordinator, f"user_{user}")
        self._user = user
        self._attr_translation_key = f"user_{user}"

    @property
    def _state(self) -> UserState:
        return self.a16.user(self._user)

    @property
    def state(self) -> MediaPlayerState | None:
        if self.a16.power is None:
            return None
        return MediaPlayerState.ON if self.a16.is_on else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        if (volume := self._state.volume) is None:
            return None
        return max(0.0, min(1.0, (volume - VOLUME_MIN) / (VOLUME_MAX - VOLUME_MIN)))

    @property
    def is_volume_muted(self) -> bool | None:
        return self._state.muted

    @property
    def source(self) -> str | None:
        return self.a16.source

    @property
    def sound_mode(self) -> str | None:
        preset = self._state.preset
        return f"Preset {preset}" if preset else None

    @property
    def media_title(self) -> str | None:
        user = self._state
        return " · ".join(part for part in (user.room, user.layout) if part) or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        user = self._state
        return {
            "a16_volume": user.volume,
            "preset": user.preset,
            "user_name": user.name,
            "layout": user.layout,
            "room": user.room,
            "headphone": user.headphone,
        }

    async def async_turn_on(self) -> None:
        await self._do(self.client.power(True))

    async def async_turn_off(self) -> None:
        await self._do(self.client.power(False))

    async def async_set_volume_level(self, volume: float) -> None:
        # No absolute volume command exists: the client steps in the background.
        self.client.set_volume(self._user, round(VOLUME_MIN + volume * (VOLUME_MAX - VOLUME_MIN)))

    async def async_volume_up(self) -> None:
        await self._do(self.client.volume_step(self._user, True))

    async def async_volume_down(self) -> None:
        await self._do(self.client.volume_step(self._user, False))

    async def async_mute_volume(self, mute: bool) -> None:
        await self._do(self.client.set_mute(self._user, mute))

    async def async_select_source(self, source: str) -> None:
        await self._do(self.client.select_source(source))

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        await self._do(self.client.select_preset(self._user, PRESETS.index(sound_mode) + 1))
