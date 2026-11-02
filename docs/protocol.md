# Protocol v2: JSON controls, packed complete gameplay frames

Endpoint `/ws`. Browser and native Pygame clients use the same protocol. Version 1
JSON-state clients must be updated with the server; mismatched joins are rejected.
The simulation is unchanged: only its transmitted representation is quantized.

## Join, identity and reliable metadata

Client sends UTF-8 JSON within five seconds:

```json
{"type":"join","v":2,"nickname":"Box"}
```

The server responds with a temporary lifetime string identity:

```json
{"type":"welcome","v":2,"you":"p000001"}
```

A complete JSON metadata message precedes the first binary frame and any frame
using a different roster revision:

```json
{"type":"metadata","v":2,"revision":"1","world":[1200,720,24,24],"physics_hz":60,"players":[[1,"p000001","Box"]]}
```

`world` is width, height, square size, paint-cell size. Metadata rows are
`[wire_slot, lifetime_identity, nickname]`. Nicknames are 1–24 printable Unicode
characters; they are labels, not accounts. Wire slots are bounded **1..200** and
are independent of lifetime strings. Slots may be reused after departure only
with a new metadata revision. Lifetime identity counters are limited to uint64;
exhaustion rejects a join before creating a body rather than wrapping an ID.

Revision is uint64, represented as a **decimal string** in JSON and read with
`BigInt` in JavaScript. This avoids silently rounding integers above 2⁵³−1. Python
uses exact integers. Metadata validates supported dimensions, counts, unique slots
and identities; conflicting mappings for the same revision are rejected.

Each immutable queued packet contains its binary frame **and its matching complete
metadata**. The one sender task for a peer sends metadata first if its revision
has not been sent, then the binary frame. Replacing an older queued packet cannot
drop a required roster event. An in-flight older packet remains internally
consistent. WebSocket ordering preserves this sequence. A receiver ignores older
revisions/ticks; future or missing metadata is a protocol error requiring reconnect,
never permission to guess an identity. A reconnect starts a fresh decoder.

## Input stays readable JSON

```json
{"type":"input","seq":12,"left":false,"right":true,"jump":false,"down":false}
```

Strict boolean buttons; strictly increasing integer `seq` in 0..2³¹−1. No extra
keys, IDs, team, coordinates, scores or teacher commands. A second join on the same
socket is rejected. An airborne jump press is consumed, not buffered until landing.

Bounds remain 512 UTF-8 bytes per incoming message, 60 messages/s with burst 90,
at most four inbound messages buffered by the CLI, and at most 160 sessions by
default (configurable up to 200), including unjoined sessions. Browser input uses a
20Hz heartbeat plus meaningful edges. Input expires after 0.5s and idle sessions
after 30s; blur, hidden tabs, settings/text entry and disconnect release buttons.
Invalid input closes with 1008; expired/slow sessions with 1001. A full world or
disallowed browser origin rejects the handshake. No account cookies are involved.

## Binary frame layout

Every frame contains **all player motion/flags/acknowledgements and all paint**.
It never requires a previous gameplay frame. Constants and names come from the
reliably synchronized metadata identified in its header. All numeric fields are
**little endian**, with no implicit struct padding. Maximum frame length is 4340
bytes (200 players, 6000 paint cells). A frame's length must match exactly:

`40 + player_count * 14 + ceil(paint_cells / 4)`

| Header byte offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | ASCII `MBX2` magic |
| 4 | uint8 | Protocol version `2` |
| 5 | uint8 | Phase: 0 waiting, 1 playing, 2 finished |
| 6 | uint16 | Complete player count, 0..200 |
| 8 | uint64 | Matching metadata revision, 1..2⁶⁴−1 |
| 16 | uint64 | Monotonic physics tick, 0..2⁵³−1 |
| 24 | uint32 | Round number |
| 28 | uint32 | Remaining round milliseconds |
| 32 | uint32 | Intermission milliseconds (zero outside finished phase) |
| 36 | uint16 | Complete paint-cell count, at most 6000 |
| 38 | uint16 | Reserved, must be zero |

Each 14-byte player record follows the header:

| Record byte offset | Type | Meaning |
| --- | --- | --- |
| 0 | uint16 | Wire slot; must occur exactly once in the matching roster |
| 2, 4 | uint16 each | X/Y: decode as `raw / 16 - 128` |
| 6 | uint8 | Angle: `raw * 2π / 256` radians |
| 7 | int16 | Vertical velocity: `raw / 8` px/s, positive is downward |
| 9 | uint8 | Bits 0–1 team (1 BLACK, 2 WHITE), bit 2 jump recharged; all other bits zero |
| 10 | uint32 | Accepted input sequence, or `0xffffffff` for no input yet |

`DataView`/`struct` handle the deliberately unaligned fields. X/Y support
−128..3967.9375px at 1/16px resolution (maximum error 1/32px); vy supports
−4096..4095.875px/s at 1/8px/s; angle has 1/256-turn resolution. These are render
quantizations; authoritative Pymunk positions, angles, forces and collisions keep
full precision. Non-finite/out-of-range values are rejected, not clamped or
truncated into another field. Input acknowledgements retain their full 31 bits.
Round/intermission clocks support at most 4294967.295 seconds; configuration
validates clock and vertical-speed bounds. Counters fail explicitly at their
supported limit rather than silently wrapping; restart the process if exhausted.

## Two-bit paint

The row-major grid follows the records. Each byte holds four cells, starting with
its **least significant two bits**. Values are 0 neutral, 1 BLACK, 2 WHITE; value 3
is invalid. Unused high padding bits in the last byte must be zero. For example,
`0120` packs to hexadecimal `24`:

```python
colour = (packed[cell_index // 4] >> (2 * (cell_index % 4))) & 3
```

The default 50×30 grid shrinks from 1500 ASCII bytes to **375 bytes**. Supported
cell sizes 12/24/40/60 divide the world; the maximum grid is 6000 cells. Scores are
derived from the complete received grid and use neutral cells in the denominator.
Last valid paint wins, with join-order painting rotated by tick each physics step.
Paint is automatic only when downward velocity exceeds the server threshold.

Python [`wire.py`](../src/multibox/wire.py) and browser
[`wire.mjs`](../src/multibox/static/wire.mjs) reconstruct the same teaching-friendly
state object: tick/time, round/phase/timers, world, paint string, coverage and rows
`[identity,nickname,team,x,y,angle,vy,jump_ready,input_seq]`. See the shared
[golden vector](../tests/fixtures/wire-v2.json), including a revision above 2⁵³,
maximum lifetime identity and input acknowledgement, signed velocity and paint.
Tests cover malformed/truncated frames, length/magic/version/flags/roster checks,
padding, maximum sizes, slot reuse, stale frames and replaced queued metadata.

## Queueing, rendering and teacher API

One packed frame is encoded per 20Hz publication, shared by all peers. Each peer
has at most one queued packet and one in-flight send, each send with a one-second
deadline. Slow senders/expiry close outside the 60Hz physics task. Metrics count
binary **and JSON welcome/metadata** payload; framing/TCP/TLS/Wi-Fi overhead is extra.
Rendering retains the existing roughly 100ms interpolation buffer and never
extrapolates physics. Input acknowledgements do not measure the entire visible
response; remote delay cannot be attributed to TCP or bandwidth from these local
measurements alone.

Teacher endpoints remain disabled (404) unless `MULTIBOX_TEACHER_TOKEN` is set.
Supply `Authorization: Bearer <token>` over localhost or trusted HTTPS:

- `POST /admin/round`, exactly `{"action":"start"}`: clear paint/input and start.
  `{"action":"reset"}`: clear and wait for the teacher, including across all rejoins.
  Bodies stay in place. Student WebSockets have no admin command.
- `GET /admin/metrics`: bounded timings, queues, bytes, metadata/frame counts,
  player counts, discarded lag, jumps and paint writes. The latest 7200 tick
  samples are retained.
- `GET /health`: public liveness, tick and player count.

The first join starts a new world. Short rounds restart after their intermission;
round clocks follow fixed simulation time. Overload records discarded catch-up
and can make a round take longer wall time. No persistence writes occur in physics.
