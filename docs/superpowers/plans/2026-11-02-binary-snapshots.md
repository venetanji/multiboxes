# Binary complete snapshots follow-up

Approved inline SOL 6.1 follow-up in existing draft PR #3, based on cbb7a060.
No other execution jobs, deployments, merges, security settings or Alive changes.

## Design

Use protocol v2: readable JSON join/input/welcome/metadata; binary complete gameplay
frames. A 40-byte little-endian versioned header carries roster revision, tick,
round/time/phase, player and paint counts. Each player is a 14-byte fixed-width
record: uint16 session wire slot, uint16 subpixel x/y, uint8 angle, int16 vertical
velocity, uint8 team/jump flags, uint32 input acknowledgement. The paint grid uses
two bits per cell, low bits first, with zero padding. Constants and nicknames live
in a complete reliable JSON roster with a uint64 revision encoded as decimal text.

Wire slots are bounded 1..200, separate from lifetime string identities. Slots can
be reused only with a new revision. Every queued immutable packet carries both its
binary frame and the matching complete roster. A single per-peer sender sends the
roster first if necessary, then the frame. Latest-only replacement therefore cannot
lose a required metadata event. Receivers validate lengths/magic/version/bounds,
reject missing/future metadata and conflicting revisions, and discard stale frames.
No frame depends on a previous gameplay snapshot. Reconnect creates a fresh decoder.

Coordinates have 1/16px resolution with a +128 offset; angle is 1/256 turn; vy is
1/8 px/s. Input acknowledgement retains the existing 31-bit input range plus an
explicit no-input sentinel. Counters and scalar bounds are checked, never wrapped
or truncated. Simulation and gameplay rules stay unchanged.

## Execution / verification

- [ ] Add failing Python/Node codec tests and shared golden vectors for every
  field, paint padding/max grid, malformed frames, counter limits and slot reuse.
- [ ] Implement codecs and reliable roster + bounded binary sender integration.
- [ ] Adapt browser, Pygame, protocol/integration tests and test bots to v2.
- [ ] Verify reconnect/reset/blur/touch/server-switch and crowded sandboxed browser.
- [ ] Run comparable 120s active 100/150-client runs at 10Hz input, then additionally
  run both at the browser's 20Hz heartbeat; include JSON metadata in egress totals.
- [ ] Update tutorial/protocol/deployment/load documentation with measured numbers,
  preserved JSON baseline, arithmetic budgets, limits and campus/TLS caveats.
- [ ] Run final tests, commit/push existing branch, update draft PR and verify exact CI SHA.

Arithmetic budget before measurement: default grid 375 bytes; frame 1815 bytes at
100 players and 2515 at 150. At 20 state Hz, aggregate gameplay payload would be
29.04 / 60.36 Mbit/s before metadata, churn, WebSocket/TCP/TLS/Wi-Fi overhead.
These are estimates, not measured results.

Approved steering in this same active cycle: connected viewport-only play,
settings/disconnect overlay and correct gameplay key ownership were prioritized.
Actual screenshots and browser checks cover desktop, phone, short/landscape,
resize, touch, focus, editing, overlay and disconnect recovery. Local behavior was
reported acceptable and the transient remote delay later improved before these
changes; do not infer that TCP or bandwidth caused it. Keep the authoritative
rendering model, preserve useful local diagnostic observations, and do not expand
into WebRTC. Include concise consenting-pair ping/HTTP troubleshooting and optional
local Docker build/run/reconnect exercises within the tutorial documentation.
