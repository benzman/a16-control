"""In-process fake of the A16 IP command server.

Models what was measured on a real unit (FW 2.17):
  * tokens NUL-terminated, messages CR-terminated
  * user A status block pushed about once a second
  * only one command is handled per "read cycle": commands arriving faster
    than `min_gap` are dropped
"""

from __future__ import annotations

import asyncio
import contextlib
import time

LAYOUT = [1, 2, 3, 4, 5, 6, 25, 26, 47, 48]  # 5.1.4h
SOURCES = {
    0x20: "eARC", 0x21: "HDMI-1", 0x22: "HDMI-2", 0x23: "HDMI-3", 0x24: "HDMI-4",
    0x25: "USB", 0x26: "LINE", 0x27: "STEREO", 0x28: "COAXIAL", 0x29: "OPTICAL",
}  # fmt: skip


def frame(*tokens: str) -> bytes:
    return b"".join(t.encode("ascii") + b"\0" for t in tokens) + b"\r"


class MockA16:
    def __init__(self, *, min_gap: float = 0.0, broadcast_interval: float = 0.2) -> None:
        self.min_gap = min_gap
        self.broadcast_interval = broadcast_interval
        self.power = "ON"
        self.source = "HDMI-1"
        self.volume = {"A": 65, "B": 65}
        self.preset = {"A": 1, "B": 1}
        self.muted = {"A": False, "B": False}
        self.solo_mode = "SOLO"
        self.test = False
        self.mode = "SVS"
        self.ht = False
        self.active = set(LAYOUT)
        self.received: list[int] = []
        self.dropped: list[int] = []
        self.connections = 0
        self.silent_connections = 0  # accept this many connections without ever answering
        self._last_handled = 0.0
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.port = 0

    async def start(self) -> MockA16:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        self.drop_clients()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def drop_clients(self) -> None:
        for writer in list(self._writers):
            writer.close()

    def push(self, *tokens: str) -> None:
        """Unsolicited message, as after an IR remote key press."""
        for writer in self._writers:
            writer.write(frame(*tokens))

    # ------------------------------------------------------------------

    def user_block(self, u: str) -> bytes:
        tokens = [
            f"{u}UR=Alice ", f"P{u}={self.preset[u]:02d}", f"V{u}={self.volume[u]}",
            f"{u}ROOM=", f"{u}NAME=", f"{u}SPKR=5.1.4h", f"{u}QFILE=Alice _NDH 30      ",
            f"{u}QNAME=Alice ", f"{u}QDATE=12:00 01/01/2024", f"{u}QTYPE=autoEQ",
            f"{u}QMOD=NDH 30      ", f"{u}TACT=ON",
        ]  # fmt: skip
        if u == "A":
            tokens += [
                f"IN={self.source}", "DEC=", "LM=0.0.0", "UMIX=OFF",
                "HTMODE=Optical", "LEG=OFF", "USER=DUAL",
            ]  # fmt: skip
        return frame(*tokens)

    def _status_tokens(self) -> list[str]:
        return [f"ALL={self.solo_mode}", f"TEST={'LOOP' if self.test else 'OFF'}", f"MODE={self.mode}"]

    def _active_tokens(self) -> list[str]:
        ids = sorted(self.active)
        if self.active == set(LAYOUT):
            ids = [0, *ids]
        return [f"A{i:02d}" for i in ids]

    def respond(self, code: int) -> bytes:
        if code == 0x2C:
            self.power = "ON"
        if code == 0x2D:
            self.power = "STANDBY"
        if code in (0x2C, 0x2D, 0x2E):
            return frame(f"PWR={self.power}")
        if code in SOURCES:
            self.source = SOURCES[code]
            return frame(f"IN={self.source}")
        if code in (0x30, 0x31, 0x33, 0x34):
            u = "A" if code < 0x33 else "B"
            step = 1 if code in (0x30, 0x33) else -1
            self.volume[u] = max(27, min(99, self.volume[u] + step))
            return frame(f"V{u}={self.volume[u]}")
        if code in (0x32, 0x35):
            u = "A" if code == 0x32 else "B"
            self.muted[u] = not self.muted[u]
            return frame(f"MUTE{u}={'MUTE' if self.muted[u] else 'OFF'}")
        if code == 0x1A:
            self.solo_mode = "MUTE" if self.solo_mode == "SOLO" else "SOLO"
            self.active = set(LAYOUT)
            return frame(f"ALL={self.solo_mode}")
        if code == 0x08:
            self.test = not self.test
            return frame(f"TEST={'LOOP' if self.test else 'OFF'}")
        if code == 0x42:
            self.ht = not self.ht
            return frame(f"HT={'ACTIVE' if self.ht else 'OFF'}")
        if code == 0x4D:
            self.mode = "SVS"
            return frame("MODE=SVS")
        if code == 0x5E:
            self.mode = {"SVS": "AV", "AV": "MIX", "MIX": "SVS"}[self.mode]
            return frame(f"MODE={self.mode}")
        if 0x70 <= code <= 0x7F:
            self.preset["A"] = code - 0x70 + 1
            return frame(f"PA={self.preset['A']:02d}")
        if 0x90 <= code <= 0x9F:
            self.preset["B"] = code - 0x90 + 1
            return frame(f"PB={self.preset['B']:02d}")
        if code == 0x80:
            return self.user_block("A")
        if code == 0xA0:
            return self.user_block("B")
        if code == 0x83:
            return frame(f"VA={self.volume['A']}")
        if code == 0xA3:
            return b"\0" + frame(f"VB={self.volume['B']}")
        if code == 0x85:
            return frame("AHTA=-11", "AHTE=9")
        if code == 0xA5:
            return frame("BHTA=0", "BHTE=0")
        if code == 0x37:
            return frame(*[f"ACH{i}=lm 2.0" for i in range(1, 25)], *[f"BCH{i}=" for i in range(1, 17)])
        if code == 0x64:
            return (
                b"A16FW=2.17 Jan 26 2024\0APMFW=APM 117 v251, Aug  6 2021\0\0\0\0HSRFW=v74.50.38\0\0\0"
                b"HTFW=1.40 May 21 2021\0A16SN=A16TEST#000001\0\r"
            )
        if code in (0x6A, 0x38):
            keys = [f"L{i}" for i in range(1, 25)] + ["AHL", "AHR", "ATL", "ATR", "BHL", "BHR", "BTL", "BTR"]
            return frame(*[f"{k}={i} " for i, k in enumerate(keys)])
        if code == 0xAE:
            return frame(*[f"V{i:02d}" for i in [0, *LAYOUT]], *self._active_tokens(), *self._status_tokens())
        if code == 0xAF:
            return frame(*self._status_tokens(), *self._active_tokens())
        if 0xB1 <= code <= 0xE2:
            speaker = code - 0xB0
            if self.solo_mode == "SOLO":
                self.active = {speaker}
                return frame("A00", f"A{speaker:02d}")
            self.active ^= {speaker}
            return frame(f"{'A' if speaker in self.active else 'M'}{speaker:02d}")
        if code == 0x59:
            return frame("PAGE=0")
        return frame(f"KEY={code:02x}")

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        if self.silent_connections:
            self.silent_connections -= 1
            with contextlib.suppress(OSError):
                while await reader.read(4096):
                    pass
            writer.close()
            return
        self._writers.add(writer)
        broadcaster = asyncio.create_task(self._broadcast(writer))
        try:
            while line := await reader.readline():
                code = int(line.strip(), 16)
                now = time.monotonic()
                if now - self._last_handled < self.min_gap:
                    self.dropped.append(code)
                    continue
                self._last_handled = now
                self.received.append(code)
                writer.write(self.respond(code))
                await writer.drain()
        except (OSError, ValueError):
            pass
        finally:
            broadcaster.cancel()
            self._writers.discard(writer)
            writer.close()

    async def _broadcast(self, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(OSError):
            while self.broadcast_interval:
                await asyncio.sleep(self.broadcast_interval)
                writer.write(self.user_block("A"))
