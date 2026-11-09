"""Home Assistant integration tests against the in-process A16 fake."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.realiser_a16.a16 import client as ha_lib_client  # noqa: F401 - see fast_a16
from custom_components.realiser_a16.const import CONF_SPEAKER_SWITCHES, DOMAIN
from tests.mock_a16 import MockA16

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fast_a16")

SERIAL = "A16TEST#000001"


@pytest.fixture(autouse=True)
def card_urls(monkeypatch):
    """The test environment has no frontend package: stub it and record the card URL."""
    urls: list[str] = []

    async def _frontend_setup(hass, config):
        return True

    monkeypatch.setattr("homeassistant.components.frontend.async_setup", _frontend_setup)
    monkeypatch.setattr(
        "custom_components.realiser_a16.add_extra_js_url", lambda hass, url: urls.append(url)
    )
    return urls


async def until(hass: HomeAssistant, predicate, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)
    await hass.async_block_till_done()


async def setup_entry(hass: HomeAssistant, mock_a16: MockA16, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Realiser A16",
        unique_id=SERIAL,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: mock_a16.port},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = entry.runtime_data.client
    await until(hass, lambda: client.state.visible_speakers and client.state.user_b.volume)
    return entry


@pytest.fixture
async def entry(hass: HomeAssistant, mock_a16: MockA16):
    entry = await setup_entry(hass, mock_a16)
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow(hass: HomeAssistant, mock_a16: MockA16):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: mock_a16.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_setup_fails_without_device(hass: HomeAssistant, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "127.0.0.1", CONF_PORT: 1})
    entry.add_to_hass(hass)
    import custom_components.realiser_a16 as integration

    real = integration.A16Client.wait_connected
    monkeypatch.setattr(integration.A16Client, "wait_connected", lambda self, t: real(self, 0.3))
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_entities(hass: HomeAssistant, entry: MockConfigEntry):
    player = hass.states.get("media_player.realiser_a16_user_a")
    assert player.state == "on"
    assert player.attributes["source"] == "HDMI-1"
    assert player.attributes["sound_mode"] == "Preset 1"
    assert player.attributes["a16_volume"] == 65
    assert round(player.attributes["volume_level"], 3) == round((65 - 27) / 72, 3)

    assert hass.states.get("remote.realiser_a16").state == "on"
    assert hass.states.get("select.realiser_a16_source").state == "HDMI-1"
    assert hass.states.get("select.realiser_a16_user_b_preset").state == "1"
    assert hass.states.get("select.realiser_a16_speaker_tap_mode").state == "solo"
    assert hass.states.get("switch.realiser_a16_power").state == "on"
    assert hass.states.get("switch.realiser_a16_test_signal").state == "off"
    assert hass.states.get("sensor.realiser_a16_user_a_layout").state == "5.1.4h"
    assert hass.states.get("sensor.realiser_a16_user_a_headphone").state == "NDH 30"
    assert hass.states.get("sensor.realiser_a16_a16_firmware").state == "2.17 Jan 26 2024"
    assert hass.states.get("binary_sensor.realiser_a16_connection").state == "on"
    assert hass.states.get("binary_sensor.realiser_a16_user_a_tactile_output").state == "on"
    assert hass.states.get("switch.realiser_a16_speaker_l") is None  # option is off


async def test_card_is_served(hass: HomeAssistant, entry: MockConfigEntry, card_urls, hass_client):
    assert card_urls == ["/realiser_a16_frontend/realiser-a16-card.js?v=1.0.0"]
    http = await hass_client()
    for name in ("realiser-a16-card.js", "protocol_gen.js"):
        response = await http.get(f"/realiser_a16_frontend/{name}")
        assert response.status == 200, name


async def test_services(hass: HomeAssistant, entry: MockConfigEntry, mock_a16: MockA16):
    async def call(domain: str, service: str, entity: str, **data) -> None:
        await hass.services.async_call(
            domain, service, {"entity_id": entity, **data}, blocking=True
        )

    await call("media_player", "select_source", "media_player.realiser_a16_user_a", source="USB")
    await until(hass, lambda: hass.states.get("select.realiser_a16_source").state == "USB")

    await call(
        "media_player", "select_sound_mode", "media_player.realiser_a16_user_b",
        sound_mode="Preset 4",
    )  # fmt: skip
    await until(hass, lambda: hass.states.get("select.realiser_a16_user_b_preset").state == "4")

    target = (72 - 27) / 72
    await call("media_player", "volume_set", "media_player.realiser_a16_user_a", volume_level=target)
    await until(hass, lambda: mock_a16.volume["A"] == 72)

    await call("media_player", "volume_mute", "media_player.realiser_a16_user_a", is_volume_muted=True)
    await until(hass, lambda: hass.states.get("switch.realiser_a16_user_a_mute").state == "on")

    mock_a16.received.clear()
    await call("remote", "send_command", "remote.realiser_a16", command=["menu", "down", "0x04"])
    await until(hass, lambda: mock_a16.received[-3:] == [0x43, 0x4B, 0x04])

    await call("select", "select_option", "select.realiser_a16_speaker_tap_mode", option="mute")
    await until(hass, lambda: mock_a16.solo_mode == "MUTE")

    await hass.services.async_call(DOMAIN, "send_command", {"command": "speaker_3"}, blocking=True)
    await until(hass, lambda: 3 not in mock_a16.active)

    await call("switch", "turn_off", "switch.realiser_a16_power")
    await until(hass, lambda: hass.states.get("media_player.realiser_a16_user_a").state == "off")


async def test_unavailable_when_disconnected(
    hass: HomeAssistant, entry: MockConfigEntry, mock_a16: MockA16
):
    client = entry.runtime_data.client
    mock_a16.drop_clients()
    await until(hass, lambda: hass.states.get("select.realiser_a16_source").state == "unavailable")
    assert hass.states.get("binary_sensor.realiser_a16_connection").state == "off"
    await until(hass, lambda: client.connected)
    await until(hass, lambda: hass.states.get("select.realiser_a16_source").state == "HDMI-1")


async def test_speaker_switches_option(hass: HomeAssistant, mock_a16: MockA16):
    entry = await setup_entry(hass, mock_a16, {CONF_SPEAKER_SWITCHES: True})
    assert hass.states.get("switch.realiser_a16_speaker_l").state == "on"
    assert hass.states.get("switch.realiser_a16_speaker_lhs1").state == "on"
    assert hass.states.get("switch.realiser_a16_speaker_lb").state == "unavailable"  # not in 5.1.4h
    await hass.config_entries.async_unload(entry.entry_id)


async def test_websocket(hass: HomeAssistant, entry: MockConfigEntry, mock_a16: MockA16, hass_ws_client):
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "realiser_a16/subscribe", "levels": True, "tracker": True})
    assert (await ws.receive_json())["success"]
    first = (await ws.receive_json())["event"]
    assert first["type"] == "state" and first["connected"] is True
    assert first["state"]["user_a"]["volume"] == 65
    assert first["state"]["visible_speakers"] == [1, 2, 3, 4, 5, 6, 25, 26, 47, 48]
    assert "levels" not in first["state"]

    seen: dict[str, dict] = {}
    async with asyncio.timeout(3):
        while not {"levels", "tracker"} <= set(seen):
            event = (await ws.receive_json())["event"]
            seen[event["type"]] = event
    assert seen["levels"]["levels"]["L5"] == 4
    assert seen["tracker"]["a"] == [-11, 9]

    await ws.send_json({"id": 2, "type": "realiser_a16/send", "commands": ["source_hdmi3"]})
    async with asyncio.timeout(3):
        while True:
            msg = await ws.receive_json()
            if msg["id"] == 2:
                assert msg["success"]
                break
    await until(hass, lambda: mock_a16.source == "HDMI-3")

    await ws.send_json({"id": 3, "type": "realiser_a16/send", "commands": ["bogus"]})
    async with asyncio.timeout(3):
        while True:
            msg = await ws.receive_json()
            if msg["id"] == 3:
                assert not msg["success"]
                break

    await ws.send_json({"id": 4, "type": "unsubscribe_events", "subscription": 1})
    await ws.close()
