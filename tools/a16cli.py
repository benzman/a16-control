#!/usr/bin/env python3
"""Small command line client for the A16 library (works without Home Assistant).

  a16cli.py HOST status              print the full state as JSON
  a16cli.py HOST watch               print state changes until Ctrl-C
  a16cli.py HOST send NAME [NAME..]  send commands (menu, vol_a_up, source_hdmi1, 0x43 ...)
  a16cli.py HOST volume a|b N        set an absolute volume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "realiser_a16"))

from a16 import DEFAULT_PORT, EVENT_STATE, A16Client


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("action", choices=["status", "watch", "send", "volume"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    opts = ap.parse_args()

    client = A16Client(opts.host, opts.port)
    await client.start()
    try:
        if not await client.wait_connected(10):
            print(f"no answer from {opts.host}:{opts.port}", file=sys.stderr)
            return 1
        if opts.action == "status":
            await asyncio.sleep(4)  # let the initial refresh complete (6 queries, 0.5 s apart)
            print(json.dumps(client.state.as_dict(), indent=2, ensure_ascii=False))
        elif opts.action == "watch":
            client.add_listener(
                lambda kind: kind == EVENT_STATE
                and print(json.dumps(client.state.as_dict(), ensure_ascii=False), flush=True)
            )
            await asyncio.Event().wait()
        elif opts.action == "send":
            await client.send_many(opts.args)
            await asyncio.sleep(1.0)
        elif opts.action == "volume":
            await client.set_volume(opts.args[0], int(opts.args[1]))
            print(client.state.user(opts.args[0]).volume)
    finally:
        await client.stop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
