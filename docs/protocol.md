# WebSocket protocol v1

Endpoint: `/ws`; UTF-8 JSON text only. A connection reserves one of at most 160
sessions by default (configurable up to 200), including unfinished joins. Server
owns identity. Disconnect removes its body; reconnect is a new identity with a
full snapshot. No resume token, accounts or private student data.

## Client → server

Within five seconds, send exactly one join:

```json
{"type":"join","v":1,"nickname":"Box"}
```

Nickname: 1–24 printable Unicode characters after trimming. Then input only:

```json
{"type":"input","seq":0,"left":false,"right":true,"jump":false,"down":false}
```

All buttons are strict booleans. `seq` is a strictly increasing integer 0 through
2³¹−1, starting afresh on a new connection. No extra keys, IDs, team, coordinates,
scores or teacher commands. A join repeated on the same socket is rejected, not
a second body. A short jump press between physics ticks is preserved once; an
airborne press is consumed rather than queued until landing.

Limits: 512 UTF-8 bytes/message, 60 messages/second with a maximum burst of 90.
CLI Uvicorn buffers at most four inbound messages per connection. Browser/native
clients send at 20 Hz and on meaningful edges. All held buttons expire after 0.5
seconds without valid input. Sessions expire after 30 seconds without input;
transport pings detect dead TCP links separately. Invalid protocol closes with
1008; timeout/slow/expired sessions close with 1001. A full world rejects a new
handshake (HTTP 403 with the ASGI server), as does a disallowed browser Origin.

## Server → client

First, a welcome (before queued state messages):

```json
{"type":"welcome","v":1,"you":"p000001","state":{"type":"state","v":1}}
```

The example abbreviates `state`; the actual welcome always contains all fields
below. Subsequent messages are full states, never dependent deltas.

### State

| Field | Meaning |
| --- | --- |
| `type`, `v` | `state`, `1` |
| `tick`, `t` | Monotonic physics tick and simulation seconds |
| `round`, `phase` | Increasing round number; `waiting`, `playing`, `finished` |
| `remaining`, `next_round_in` | Round seconds remaining / finished intermission seconds |
| `world` | `[1200,720,24,24]`: width, height, square size, paint-cell size |
| `paint` | Complete row-major string of `0` neutral, `1` BLACK, `2` WHITE |
| `coverage` | Percentages `[neutral,BLACK,WHITE]`, each rounded independently |
| `players` | Complete roster of rows described below |

| Player row index | Meaning |
| --- | --- |
| 0 | Server-generated temporary player ID |
| 1 | Nickname |
| 2 | Team: 1 BLACK, 2 WHITE |
| 3, 4 | Authoritative x, y in screen coordinates (positive y down) |
| 5 | Rotation in radians |
| 6 | Vertical velocity (positive = descending) |
| 7 | Jump recharged boolean |
| 8 | Latest accepted input sequence, −1 before any input |

A 24px paint grid has 50×30 = 1500 cells. Config allows at most 6000. Painting
uses descending (`vy > paint_min_speed`) shape bounds. Each physics tick processes
players in join order rotated by `tick % player_count`; the last valid writer of
a cell wins. This is deterministic for the same join/input/tick sequence and
avoids permanent priority for one join position. Scores change with cell ownership
and always match the grid. Physics collisions themselves are resolved by Pymunk.

Jump support requires a sufficiently upward-facing contact below the square's
centre (in screen coordinates the normal from player toward support has y ≥ 0.65).
After an impulse, the square must lose supporting contact before that contact can
recharge it. No held-key repeats, side bumps or ceiling contacts grant flight.

Each published state is serialized once. Each client has at most one queued
snapshot and one in-flight send; a full queue replaces its older full state. The
send task has a one-second deadline. Transport high-water marks and a bounded
incoming queue also apply; this is not an unbounded stream of executor jobs.
Metrics retain only the latest 7200 tick samples. Socket expiry/close runs outside
the physics task. Rendering interpolates with about 100ms delay and drops departed
players from complete rosters; reset/rejoin do not depend on previously seen events.

## Teacher HTTP API

Disabled (404) unless `MULTIBOX_TEACHER_TOKEN` is set in the server process. Supply
`Authorization: Bearer <token>` over a trusted local connection or HTTPS:

- `POST /admin/round` with exactly `{"action":"start"}` starts a fresh round and
  clears paint/held input. `{"action":"reset"}` clears and waits for teacher start.
  Bodies stay in place, avoiding forced respawns in a crowded live world.
- `GET /admin/metrics` returns bounded timing distributions, delivery/queue counts,
  player/session counts, discarded catch-up time, paint writes and jump count.
- `GET /health` is public and returns liveness, tick and connected-player count.

By default the first join starts a new world. A teacher reset waits for `start`,
including if everyone leaves and rejoins. Round clocks follow fixed simulation time. An overloaded process
records discarded lag and can take longer wall time; use measured capacity limits.
