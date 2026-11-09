"""State model of a Realiser A16, filled by the parser."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UserState:
    """Per-user (A or B) preset information."""

    name: str | None = None  # AUR / BUR
    preset: int | None = None  # PA / PB
    volume: int | None = None  # VA / VB
    tri_level: int | None = None  # TRI (only when tri-level is enabled)
    muted: bool | None = None  # MUTEA / MUTEB - only known after a mute toggle
    room: str | None = None  # AROOM
    subject: str | None = None  # ANAME
    layout: str | None = None  # ASPKR
    hpeq_file: str | None = None  # AQFILE
    hpeq_subject: str | None = None  # AQNAME
    hpeq_date: str | None = None  # AQDATE
    hpeq_type: str | None = None  # AQTYPE
    headphone: str | None = None  # AQMOD
    tactile: bool | None = None  # ATACT
    assignments: dict[int, str] = field(default_factory=dict)  # ACHn / BCHn
    ht_azimuth: int | None = None  # AHTA / BHTA
    ht_elevation: int | None = None  # AHTE / BHTE


@dataclass
class A16State:
    """Everything the A16 reports over the IP command server."""

    power: str | None = None  # PWR: ON / STANDBY / BOOT
    source: str | None = None  # IN
    decoder: str | None = None  # DEC ("Audio" in Centro)
    format: str | None = None  # LM ("Format" in Centro)
    upmixer: str | None = None  # UMIX
    ht_mode: str | None = None  # HTMODE
    legacy: str | None = None  # LEG
    user_mode: str | None = None  # USER: SINGLE / DUAL
    mode: str | None = None  # MODE: SVS / AV / MIX
    solo_mode: str | None = None  # ALL: SOLO / MUTE
    test: bool | None = None  # TEST: LOOP / OFF
    ht_active: bool | None = None  # HT: ACTIVE / OFF - only known after HT key
    page: int | None = None  # PAGE (menu page, 0 = home)
    last_key: str | None = None  # KEY=nn acknowledgement
    user_a: UserState = field(default_factory=UserState)
    user_b: UserState = field(default_factory=UserState)
    visible_speakers: set[int] = field(default_factory=set)
    active_speakers: set[int] = field(default_factory=set)
    all_active: bool | None = None  # A00 present in the last snapshot
    levels: dict[str, int] = field(default_factory=dict)  # L1..L24, AHL, AHR, ATL, ...
    firmware: dict[str, str] = field(default_factory=dict)  # A16FW, APMFW, HSRFW, HTFW, A16SN
    unknown: dict[str, str] = field(default_factory=dict)

    @property
    def is_on(self) -> bool:
        return self.power == "ON"

    @property
    def serial(self) -> str | None:
        return self.firmware.get("A16SN")

    def user(self, which: str) -> UserState:
        """Return the user state for 'a' or 'b'."""
        return self.user_a if which.lower() == "a" else self.user_b

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot (sets become sorted lists)."""
        data = asdict(self)
        data["visible_speakers"] = sorted(self.visible_speakers)
        data["active_speakers"] = sorted(self.active_speakers)
        return data
