"""WebSocket API for the Lovelace card.

realiser_a16/subscribe  pushes the full state on every change and, while the
                        subscription asks for them, level meters and head
                        tracker angles (these never become entities: at 2 Hz
                        they would only fill the recorder).
realiser_a16/send       sends commands by name.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .a16 import EVENT_CONNECTION, EVENT_LEVELS, EVENT_STATE, EVENT_TRACKER, A16Error


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_send)


def _coordinator(hass: HomeAssistant, msg: dict[str, Any]):
    from . import get_coordinator

    return get_coordinator(hass, msg.get("entry_id"))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "realiser_a16/subscribe",
        vol.Optional("entry_id"): cv.string,
        vol.Optional("levels", default=False): cv.boolean,
        vol.Optional("tracker", default=False): cv.boolean,
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    try:
        coordinator = _coordinator(hass, msg)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return
    client = coordinator.client

    def _state_event() -> dict[str, Any]:
        state = client.state.as_dict()
        state.pop("levels")
        return {"type": "state", "connected": client.connected, "state": state}

    @callback
    def _forward(kind: str) -> None:
        if kind in (EVENT_STATE, EVENT_CONNECTION):
            event = _state_event()
        elif kind == EVENT_LEVELS and msg["levels"]:
            event = {"type": "levels", "levels": client.state.levels}
        elif kind == EVENT_TRACKER and msg["tracker"]:
            a, b = client.state.user_a, client.state.user_b
            event = {
                "type": "tracker",
                "a": [a.ht_azimuth, a.ht_elevation],
                "b": [b.ht_azimuth, b.ht_elevation],
            }
        else:
            return
        connection.send_message(websocket_api.event_message(msg["id"], event))

    unsubscribers = [client.add_listener(_forward)]
    if msg["levels"]:
        unsubscribers.append(client.subscribe_fast(EVENT_LEVELS))
    if msg["tracker"]:
        unsubscribers.append(client.subscribe_fast(EVENT_TRACKER))

    @callback
    def _unsubscribe() -> None:
        for unsubscribe in unsubscribers:
            unsubscribe()

    connection.subscriptions[msg["id"]] = _unsubscribe
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(msg["id"], _state_event()))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "realiser_a16/send",
        vol.Optional("entry_id"): cv.string,
        vol.Required("commands"): vol.All(cv.ensure_list, [cv.string]),
    }
)
@websocket_api.async_response
async def ws_send(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    try:
        await _coordinator(hass, msg).client.send_many(msg["commands"])
    except (A16Error, HomeAssistantError) as err:
        connection.send_error(msg["id"], "send_failed", str(err))
        return
    connection.send_result(msg["id"])
