"""Smyth Realiser A16 integration."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .a16 import A16Client, A16Error
from .const import CARD_FILE, DOMAIN, FRONTEND_URL
from .coordinator import A16ConfigEntry, A16Coordinator
from .websocket_api import async_register_websocket_api

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_COMMAND = "send_command"
ATTR_COMMAND = "command"
ATTR_ENTRY_ID = "entry_id"

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


def get_coordinator(hass: HomeAssistant, entry_id: str | None = None) -> A16Coordinator:
    """Return the coordinator for an entry id, or the only/first loaded one."""
    entries: list[A16ConfigEntry] = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and (entry_id is None or entry.entry_id == entry_id)
    ]
    if not entries:
        raise ServiceValidationError("No loaded Realiser A16 found")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card, the websocket API and the services."""
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL}/{CARD_FILE}?v={integration.version}")
    async_register_websocket_api(hass)

    async def _send_command(call: ServiceCall) -> None:
        coordinator = get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        try:
            await coordinator.client.send_many(call.data[ATTR_COMMAND])
        except A16Error as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, _send_command, SEND_COMMAND_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: A16ConfigEntry) -> bool:
    """Connect to the A16 and set up the platforms."""
    client = A16Client(entry.data[CONF_HOST], entry.data[CONF_PORT])
    await client.start()
    if not await client.wait_connected(20):
        await client.stop()
        raise ConfigEntryNotReady(
            f"Realiser A16 at {client.host}:{client.port} does not answer "
            "(is the TCP command server enabled?)"
        )

    coordinator = A16Coordinator(hass, entry, client)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: A16ConfigEntry) -> bool:
    """Unload the platforms and close the connection."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: A16ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
