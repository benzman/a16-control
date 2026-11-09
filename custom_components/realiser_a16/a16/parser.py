"""Incremental parser for the A16 response stream.

Wire format (verified on FW 2.17):
  * a message is a sequence of tokens, each terminated by NUL
  * a message is terminated by CR
  * tokens are KEY=VALUE, or bare Vnn / Ann / Mnn speaker tokens
  * values may carry padding spaces; padding NULs produce empty tokens
"""

from __future__ import annotations

import re

from .state import A16State, UserState

# What a message touched. The client uses these to decide whom to notify
# and which follow-up queries to send.
STATE = "state"  # something in the persistent state changed
LEVELS = "levels"
TRACKER = "tracker"
USER_A_BLOCK = "user_a_block"  # periodic user A broadcast seen
RESPONSE = "response"  # a message other than the user A block: answers a command
NEED_SPEAKERS = "need_speakers"  # active speaker set is stale -> query 'af'
NEED_LAYOUT = "need_layout"  # preset/layout changed -> query 'ae', '37', 'a0'

_MAX_BUFFER = 65536
_SPEAKER_TOKEN = re.compile(r"^([VAM])(\d{2})$")
_CHANNEL_KEY = re.compile(r"^([AB])CH(\d+)$")
_LEVEL_KEY = re.compile(r"^(L\d+|[AB][HT][LR])$")
_FIRMWARE_KEYS = {"A16FW", "APMFW", "HSRFW", "HTFW", "A16SN"}

# key suffix -> UserState attribute, for string fields prefixed with A or B
_USER_TEXT = {
    "UR": "name",
    "ROOM": "room",
    "NAME": "subject",
    "SPKR": "layout",
    "QFILE": "hpeq_file",
    "QNAME": "hpeq_subject",
    "QDATE": "hpeq_date",
    "QTYPE": "hpeq_type",
    "QMOD": "headphone",
}
_GLOBAL_TEXT = {
    "IN": "source",
    "DEC": "decoder",
    "LM": "format",
    "UMIX": "upmixer",
    "HTMODE": "ht_mode",
    "LEG": "legacy",
    "USER": "user_mode",
    "PWR": "power",
    "MODE": "mode",
    "KEY": "last_key",
}


def _to_int(text: str) -> int | None:
    match = re.match(r"\s*(-?\d+)", text)
    return int(match.group(1)) if match else None


class A16Parser:
    """Feed raw bytes, get the state updated in place."""

    def __init__(self, state: A16State | None = None) -> None:
        self.state = state if state is not None else A16State()
        self._buf = b""
        self._touched: set[str] = set()

    def feed(self, data: bytes) -> set[str]:
        """Consume bytes; return the categories touched by completed messages."""
        self._touched = set()
        self._buf += data
        while (end := self._buf.find(b"\r")) >= 0:
            message, self._buf = self._buf[:end], self._buf[end + 1 :]
            self._message(message)
        if len(self._buf) > _MAX_BUFFER:  # no terminator in sight: don't grow forever
            message, self._buf = self._buf, b""
            self._message(message)
        return self._touched

    # ------------------------------------------------------------------

    def _set(self, obj: object, attr: str, value: object) -> None:
        if getattr(obj, attr) != value:
            setattr(obj, attr, value)
            self._touched.add(STATE)

    def _message(self, raw: bytes) -> None:
        pairs: list[tuple[str, str]] = []
        speakers: dict[str, set[int]] = {"V": set(), "A": set(), "M": set()}
        for chunk in raw.split(b"\0"):
            token = chunk.decode("ascii", errors="replace").strip()
            if not token:
                continue
            if "=" in token:
                key, _, value = token.partition("=")
                pairs.append((key.strip(), value.strip()))
            elif match := _SPEAKER_TOKEN.match(token):
                speakers[match.group(1)].add(int(match.group(2)))
            else:
                self._set_item(self.state.unknown, token, "")

        if (pairs or any(speakers.values())) and all(key != "AUR" for key, _ in pairs):
            self._touched.add(RESPONSE)
        for key, value in pairs:
            self._pair(key, value)
        self._speakers(speakers, {key for key, _ in pairs})

    def _set_item(self, mapping: dict, key: object, value: object) -> None:
        if key not in mapping or mapping[key] != value:
            mapping[key] = value
            self._touched.add(STATE)

    def _pair(self, key: str, value: str) -> None:
        state = self.state

        if key in _GLOBAL_TEXT:
            self._set(state, _GLOBAL_TEXT[key], value)
        elif key == "ALL":
            if state.solo_mode != value:
                self._touched.add(NEED_SPEAKERS)
            self._set(state, "solo_mode", value)
        elif key == "TEST":
            self._set(state, "test", value != "OFF")
        elif key == "HT":
            self._set(state, "ht_active", value == "ACTIVE")
        elif key == "PAGE":
            self._set(state, "page", _to_int(value))
        elif key in ("MUTEA", "MUTEB"):
            self._set(state.user(key[-1]), "muted", value == "MUTE")
        elif key in ("VA", "VB"):
            user = state.user(key[-1])
            self._set(user, "volume", _to_int(value))
            if "TRI=" in value:
                self._set(user, "tri_level", _to_int(value.split("TRI=", 1)[1]))
        elif key == "TRI":
            self._set(state.user_a, "tri_level", _to_int(value))
        elif key in ("PA", "PB"):
            user = state.user(key[-1])
            preset = _to_int(value)
            if user.preset is not None and user.preset != preset:
                self._touched.add(NEED_LAYOUT)
            self._set(user, "preset", preset)
        elif key in ("AHTA", "AHTE", "BHTA", "BHTE"):
            attr = "ht_azimuth" if key[-1] == "A" else "ht_elevation"
            setattr(state.user(key[0]), attr, _to_int(value))
            self._touched.add(TRACKER)
        elif _LEVEL_KEY.match(key):
            state.levels[key] = _to_int(value) or 0
            self._touched.add(LEVELS)
        elif key in _FIRMWARE_KEYS:
            self._set_item(state.firmware, key, value)
        elif match := _CHANNEL_KEY.match(key):
            self._set_item(state.user(match.group(1)).assignments, int(match.group(2)), value)
        elif key in ("ATACT", "BTACT"):
            self._set(state.user(key[0]), "tactile", value == "ON")
        elif key[:1] in ("A", "B") and key[1:] in _USER_TEXT:
            user: UserState = state.user(key[0])
            attr = _USER_TEXT[key[1:]]
            if attr == "layout" and user.layout not in (None, value):
                self._touched.add(NEED_LAYOUT)
            if key == "AUR":
                self._touched.add(USER_A_BLOCK)
            self._set(user, attr, value)
        else:
            self._set_item(state.unknown, key, value)

    def _speakers(self, tokens: dict[str, set[int]], keys: set[str]) -> None:
        state = self.state
        visible, active, muted = tokens["V"], tokens["A"], tokens["M"]

        if visible:
            self._set(state, "visible_speakers", visible - {0})

        if active and (visible or "ALL" in keys):
            # 'ae' / 'af' answer: complete list of active speakers
            self._set(state, "active_speakers", active - {0})
            self._set(state, "all_active", 0 in active)
            self._touched.discard(NEED_SPEAKERS)
        elif active or muted:
            # answer to a speaker select: only a delta, ask for the full list
            self._set(state, "active_speakers", (state.active_speakers | (active - {0})) - muted)
            self._touched.add(NEED_SPEAKERS)
