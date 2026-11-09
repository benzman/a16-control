"""Shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# The protocol library is importable on its own, without Home Assistant.
sys.path.insert(0, str(ROOT / "custom_components" / "realiser_a16"))
sys.path.insert(0, str(ROOT))

from tests.mock_a16 import MockA16


@pytest.fixture
async def mock_a16():
    server = await MockA16().start()
    yield server
    await server.stop()


@pytest.fixture
def fast_a16(monkeypatch):
    """Remove the real-device pacing so tests run quickly."""
    import a16.client as lib_client

    modules = [lib_client]
    with_ha = sys.modules.get("custom_components.realiser_a16.a16.client")
    if with_ha:
        modules.append(with_ha)
    for module in modules:
        monkeypatch.setattr(module, "SEND_GAP", 0.0)
        monkeypatch.setattr(module, "ACK_TIMEOUT", 0.3)
        monkeypatch.setattr(module, "LAYOUT_REFRESH_DELAY", 0.05)
        monkeypatch.setattr(module, "FAST_POLL", 0.05)
        monkeypatch.setattr(module, "VOLUME_SETTLE", 0.15)
        monkeypatch.setattr(module, "RECONNECT_MIN", 0.05)
        monkeypatch.setattr(module, "RECONNECT_GAP", 0.05)
        monkeypatch.setattr(module, "FIRST_DATA_TIMEOUT", 0.4)


@pytest.fixture(autouse=True)
def _allow_localhost(socket_enabled):
    """The Home Assistant test plugin blocks sockets; the fake A16 listens on 127.0.0.1."""
