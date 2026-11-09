# Realiser A16 IP command protocol – as measured

Source: *A16 IP (TCP) Command Summary*, S. Smyth, 5 May 2020, plus measurements on a unit
with firmware 2.17 (Jan 26 2024) on 9 Nov 2026. Where the two disagree, the measurement is
what the code follows. All command codes live in `a16_protocol.json`.

## Transport

- TCP, fixed IP and port set on the A16 (Settings → Network, default port 4101).
  "TCP command server" must be on.
- Send: two hex digits + `\r\n`, e.g. `43\r\n` for MENU.
- Receive: tokens, each terminated by NUL (`\0`); a message ends with CR (`\r`).
  Tokens are `KEY=VALUE` or bare speaker tokens (`V01`, `A01`, `M01`).
- Values may be padded with spaces (`AQMOD=NDH 30      `, `L1=0 `); the firmware answer
  contains runs of padding NULs. Strip values, ignore empty tokens.
- There is no request id. Answers and unsolicited messages share the stream, so a client
  keeps a state object up to date instead of matching answers to requests.

## Timing – the important part

| Observation | Consequence |
|---|---|
| The A16 handles **one command at a time** and silently drops the rest. Ten queries sent 50 ms apart: 2 answered. 300 ms apart: 13 of 20. 500 ms: 20 of 20. Even at 0.5–1 s roughly one key command in ten can still go missing. | The client keeps one command in flight: at least 0.5 s between sends (`SEND_GAP`), wait for the answer (0.2–1.1 s), repeat once if none arrives within 2 s. Measured that way: 48 of 48 commands answered first time. |
| Commands sent right after connecting are dropped more often. | Wait one gap after connect before the first command. |
| With "TCP slave response" on, the user A info block (same as the answer to `80`) is pushed about once a second. | User A, source and audio status need no polling. The stream also acts as keep-alive. |
| Power state and user B are **not** pushed. | Poll `2e` and `a0` every 10 s. |
| Mute (`MUTEA`/`MUTEB`) and head tracker on/off (`HT`) are only reported as the answer to their toggle key. | Unknown until first use; shown as "assumed state". |

Because of the 0.5 s spacing, an absolute volume change of 8 steps takes about 4 s.
There is no absolute volume command.

## Connections – how to lock yourself out

- The A16 serves **one** TCP connection. A second one is accepted at TCP level (or times
  out) but gets no data.
- It needs a moment to notice that a connection was closed. A connection opened right
  after another one closed is accepted and then never served – no push, no answers.
- Observed in Home Assistant with a 1 s reconnect delay: the unserved connection timed out
  after 30 s, the client reconnected 1 s later, and that connection was not served either.
  This repeated indefinitely. After roughly 30 minutes of it (plus about 30 short test
  connections) the command server stopped answering altogether and did not recover on its
  own within several minutes.
- The client therefore waits 5 s after any disconnect before connecting (`RECONNECT_GAP`),
  counts a connection as up only once data arrived, and doubles the retry delay (5 s up to
  120 s) while the A16 stays silent.

## Messages

User A block (pushed, or answer to `80`):

```
AUR=Alice  PA=01 VA=65 AROOM= ANAME= ASPKR=5.1.4h AQFILE=… AQNAME=… AQDATE=12:00 01/01/2024
AQTYPE=autoEQ AQMOD=NDH 30 ATACT=ON IN=HDMI-1 DEC= LM=0.0.0 UMIX=OFF HTMODE=Optical LEG=OFF USER=DUAL
```

`AQDATE` is not in the 2020 document. Centro labels: `DEC` = Audio, `LM` = Format,
`AROOM` = Listening room, `ANAME` = Subject, `ASPKR` = Layout, `AQMOD` = Headphone.
User B block (`a0`) has the same keys with a `B` prefix, without the global ones.

| Command | Answer on FW 2.17 |
|---|---|
| `2e` power status | `PWR=ON` / `STANDBY` / `BOOT` |
| `83` / `a3` volume | `VA=65` / `VB=65` (`TRI=` only with tri-level enabled) |
| `85` / `a5` head tracker | `AHTA=-11 AHTE=9` / `BHTA=0 BHTE=0` – azimuth and elevation as **two** keys (document says `AHT=string`) |
| `37` assignments | `ACH1..ACH24`, `BCH1..BCH16` |
| `64` firmware | `A16FW`, `APMFW`, `HSRFW`, `HTFW`, `A16SN` |
| `6a` levels | `L1..L24`, then `AHL AHR ATL ATR BHL BHR BTL BTR` (HP and tactile, left/right, per user) |
| `ae` speaker visibility | `V00 V01 …` then `A00 A01 …` then `ALL=SOLO TEST=OFF MODE=SVS` |
| `af` active speakers | `ALL=SOLO TEST=OFF MODE=SVS` then `A00 A01 …` |

## Speakers

- IDs are **1-based** and match table 3 of the document (1 = L, 2 = R, 3 = C, 4 = SW …).
  Token `00` is not a speaker: `A00` means "all active".
  Example 5.1.4h: `V01–V06, V25, V26, V47, V48` = L R C SW Ls Rs Lh Rh Lhs1 Rhs1.
- Select speaker *n* (1–50): code `b0 + n`. In solo mode the answer is `A00 Ann`; in mute
  mode it toggles `Ann` / `Mnn`. That answer is only a delta, so the client asks `af`
  afterwards for the full list.
- `1a` (ALL key) switches between solo and mute mode: `ALL=SOLO` / `ALL=MUTE`.

## Key commands, verified

| Sent | Answer |
|---|---|
| `30` / `31` volume A up/down | `VA=66`, sent twice about 0.1 s apart |
| `32` mute A | `MUTEA=MUTE`, next press `MUTEA=OFF`; followed by an unsolicited speaker status message |
| `43` MENU | `KEY=43` |
| `59` BACK | `PAGE=0` (after about 1.1 s) |

## Not yet verified on the device

Taken from the document only: answers to source, preset, speaker select, ALL, TEST, HT and
power commands; behaviour in standby (does the user A push continue?); the inactivity
timeout; and whether a second TCP client is accepted while one is connected.
