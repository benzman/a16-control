"""Config flow for the Realiser A16."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .a16 import DEFAULT_PORT, A16ConnectionError, async_fetch_info
from .const import CONF_SPEAKER_SWITCHES, DOMAIN, MODEL
from .coordinator import A16ConfigEntry


class A16ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for host and port, verify by reading the firmware info."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            try:
                info = await async_fetch_info(host, port)
            except A16ConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info.serial or f"{host}:{port}")
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(
                    title=MODEL, data={CONF_HOST: host, CONF_PORT: port}
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: A16ConfigEntry) -> OptionsFlow:
        return A16OptionsFlow()


class A16OptionsFlow(OptionsFlow):
    """Options: per-speaker switch entities."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema({vol.Required(CONF_SPEAKER_SWITCHES, default=False): cv.boolean})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
