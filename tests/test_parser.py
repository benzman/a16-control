"""Parser tests, including a replay of bytes recorded from a real A16 (FW 2.17)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from a16 import A16Parser, resolve_command
from a16 import parser as p

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "probe_2026-11-09.jsonl"


def replay(chunk_size: int | None = None) -> A16Parser:
    parser = A16Parser()
    data = b"".join(bytes.fromhex(json.loads(line)["hex"]) for line in FIXTURE.read_text().splitlines())
    if chunk_size is None:
        parser.feed(data)
    else:
        for start in range(0, len(data), chunk_size):
            parser.feed(data[start : start + chunk_size])
    return parser


def test_real_capture():
    state = replay().state
    assert state.power == "ON"
    assert state.source == "HDMI-1"
    assert state.user_mode == "DUAL"
    assert state.ht_mode == "Optical"
    assert state.format == "0.0.0"
    assert state.mode == "SVS"
    assert state.solo_mode == "SOLO"
    assert state.test is False

    a, b = state.user_a, state.user_b
    assert (a.name, a.preset, a.volume, a.layout) == ("Alice", 1, 65, "5.1.4h")
    assert (b.name, b.preset, b.volume, b.layout) == ("Alice", 1, 65, "5.1.4h")
    assert a.headphone == "NDH 30"  # padding stripped
    assert a.hpeq_file == "Alice _NDH 30"
    assert a.hpeq_date == "12:00 01/01/2024"
    assert a.tactile is True
    assert (a.ht_azimuth, a.ht_elevation) == (-11, 9)
    assert (b.ht_azimuth, b.ht_elevation) == (0, 0)
    assert len(a.assignments) == 24 and len(b.assignments) == 16
    assert a.assignments[6] == "lm 4.0.2h"

    # 5.1.4h: L R C SW Ls Rs Lh Rh Lhs1 Rhs1 - IDs are 1-based, 00 is the ALL marker
    assert state.visible_speakers == {1, 2, 3, 4, 5, 6, 25, 26, 47, 48}
    assert state.active_speakers == state.visible_speakers
    assert state.all_active is True

    assert state.firmware == {
        "A16FW": "2.17 Jan 26 2024",
        "APMFW": "APM 117 v251, Aug  6 2021",
        "HSRFW": "v74.50.38",
        "HTFW": "1.40 May 21 2021",
        "A16SN": "A160X0000#000000",
    }
    assert set(state.levels) == {f"L{i}" for i in range(1, 25)} | {
        "AHL", "AHR", "ATL", "ATR", "BHL", "BHR", "BTL", "BTR",
    }  # fmt: skip
    assert state.unknown == {}


def test_chunking_does_not_matter():
    assert replay(1).state == replay().state
    assert replay(7).state == replay().state


def test_incomplete_message_waits_for_terminator():
    parser = A16Parser()
    assert parser.feed(b"PWR=STAND") == set()
    assert parser.state.power is None
    assert p.STATE in parser.feed(b"BY\0\r")
    assert parser.state.power == "STANDBY"


def test_unchanged_message_is_not_a_change():
    parser = A16Parser()
    assert p.STATE in parser.feed(b"VA=65\0\r")
    assert p.STATE not in parser.feed(b"VA=65\0\r")


def test_key_responses():
    parser = A16Parser()
    parser.feed(b"VA=70 TRI=2\0\rMUTEA=MUTE\0\rMUTEB=OFF\0\rHT=ACTIVE\0\rTEST=LOOP\0\r")
    parser.feed(b"KEY=43\0\rPAGE=12\0\rMODE=AV\0\rTRI=3\0\r")
    state = parser.state
    assert state.user_a.volume == 70
    assert state.user_a.muted is True and state.user_b.muted is False
    assert state.ht_active is True and state.test is True
    assert (state.last_key, state.page, state.mode) == ("43", 12, "AV")
    assert state.user_a.tri_level == 3


def test_levels_and_tracker_are_not_state_changes():
    parser = A16Parser()
    assert parser.feed(b"L1=42 \0AHL=7 \0\r") == {p.LEVELS, p.RESPONSE}
    assert parser.state.levels == {"L1": 42, "AHL": 7}
    assert parser.feed(b"AHTA=-4\0AHTE=9\0\r") == {p.TRACKER, p.RESPONSE}


def test_user_a_block_is_not_a_response():
    parser = A16Parser()
    touched = parser.feed(b"AUR=Alice \0PA=01\0VA=65\0\r")
    assert p.USER_A_BLOCK in touched and p.RESPONSE not in touched
    assert p.RESPONSE in parser.feed(b"KEY=43\0\r")


def test_speaker_delta_requests_full_status():
    parser = A16Parser()
    parser.feed(b"V00\0V01\0V02\0V03\0A00\0A01\0A02\0A03\0ALL=MUTE\0TEST=OFF\0MODE=SVS\0\r")
    assert parser.state.active_speakers == {1, 2, 3}
    touched = parser.feed(b"M02\0\r")
    assert p.NEED_SPEAKERS in touched
    assert parser.state.active_speakers == {1, 3}
    # the full answer to 'af' settles it
    touched = parser.feed(b"ALL=MUTE\0TEST=OFF\0MODE=SVS\0A01\0A03\0\r")
    assert p.NEED_SPEAKERS not in touched
    assert parser.state.all_active is False


def test_preset_change_requests_layout():
    parser = A16Parser()
    assert p.NEED_LAYOUT not in parser.feed(b"PA=01\0\r")  # first sighting
    assert p.NEED_LAYOUT in parser.feed(b"PA=02\0\r")
    assert p.NEED_LAYOUT not in parser.feed(b"PA=02\0\r")


def test_unknown_tokens_are_kept():
    parser = A16Parser()
    parser.feed(b"NEWKEY=1\0\r")
    assert parser.state.unknown == {"NEWKEY": "1"}


def test_resolve_command():
    assert resolve_command("menu") == 0x43
    assert resolve_command("MENU") == 0x43
    assert resolve_command("1") == 0x5D  # digit key, not code 0x01
    assert resolve_command("0x43") == 0x43
    assert resolve_command("power_on") == 0x2C
    assert resolve_command("source_hdmi2") == 0x22
    assert resolve_command("preset_a_1") == 0x70
    assert resolve_command("preset_b_16") == 0x9F
    assert resolve_command("speaker_1") == 0xB1
    assert resolve_command("speaker_50") == 0xE2
    for bad in ("nope", "preset_a_17", "speaker_51", "source_vhs", "0x1ff"):
        try:
            resolve_command(bad)
        except Exception as err:  # noqa: BLE001
            assert "Unknown" in str(err) or "range" in str(err)
        else:
            raise AssertionError(bad)


def test_generated_files_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_protocol.py"), "--check"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout
