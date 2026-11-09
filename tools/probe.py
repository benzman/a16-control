#!/usr/bin/env python3
"""Record raw A16 responses for read-only queries.

Usage: probe.py HOST [PORT] [--out FILE] [--listen SECONDS] [CODE ...]

Writes one JSON line per received chunk: {"t": seconds, "cmd": "80"|null, "hex": "..."}
Only query commands are sent by default; nothing that changes device state.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time

READ_ONLY = ["2e", "80", "a0", "83", "a3", "85", "a5", "37", "64", "6a", "ae", "af"]


def drain(sock: socket.socket, seconds: float, t0: float, cmd: str | None, out) -> bytes:
    """Read everything arriving within `seconds`, logging each chunk."""
    data = b""
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(65536)
        except TimeoutError:
            break
        if not chunk:
            print("!! connection closed by A16", file=sys.stderr)
            raise SystemExit(1)
        rec = {"t": round(time.monotonic() - t0, 4), "cmd": cmd, "hex": chunk.hex()}
        out.write(json.dumps(rec) + "\n")
        data += chunk
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("port", nargs="?", type=int, default=4101)
    ap.add_argument("--out", default="-")
    ap.add_argument("--listen", type=float, default=3.0, help="passive listen before/after")
    ap.add_argument("--wait", type=float, default=1.5, help="wait per command")
    ap.add_argument("codes", nargs="*", default=READ_ONLY)
    args = ap.parse_args()

    out = sys.stdout if args.out == "-" else open(args.out, "w")
    t0 = time.monotonic()
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        print(f"connected in {time.monotonic() - t0:.3f}s", file=sys.stderr)
        idle = drain(sock, args.listen, t0, None, out)
        print(f"[idle] {idle!r}", file=sys.stderr)
        for code in args.codes:
            sock.sendall(f"{code}\r\n".encode("ascii"))
            data = drain(sock, args.wait, t0, code, out)
            print(f"[{code}] {len(data)}B {data!r}", file=sys.stderr)
        idle = drain(sock, args.listen, t0, None, out)
        print(f"[idle] {idle!r}", file=sys.stderr)
    if out is not sys.stdout:
        out.close()


if __name__ == "__main__":
    main()
