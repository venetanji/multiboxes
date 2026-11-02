# Browser territory implementation plan

> Implement inline using the executing-plans and verification-before-completion skills.

**Goal:** A reviewable classroom physics/paint game, delivered as a draft PR.

**Architecture:** Extract the useful Pymunk world into a transport-independent
simulation. An asyncio hub steps it at 60 Hz and publishes complete shared snapshots
at 20 Hz to bounded independent senders. Browser and optional Pygame clients share
one WebSocket protocol.

**Tech stack:** Python 3.11+, Pymunk, FastAPI, Uvicorn, WebSockets, Canvas, pytest,
Node test runner, sandboxed Chromium via the existing Docker tooling.

**Spec:** [Approved scope](../../design.md), plus the delegated task brief.

## Global constraints

- Separate verified venetanji/multiboxes checkout, branch from current main.
- No Alive/teaching/PFAD edits; no deployments, server changes, merge or release.
- Server owns team, identity, physics, jump, paint and scores. No database/accounts.
- Left/right; fresh jump with support recharge; down-force; descending-only paint.
- Full snapshots, one queued state per client, bounded inputs and lifecycle cleanup.
- Same static client for local HTTP and optional hosted HTTPS/WSS use.
- Retain useful native rendering on the same authoritative world.

## Review focus

- Jump repress during the original landing contact must not enable flight.
- A sender blocked in TCP must not block simulation or retain unbounded states.
- Late events from an old socket must not affect a switched server session.
- Round reset/reconnect must replace the complete grid, roster and input state.
- Empty/malformed/oversized joins, spoofed state and stale input must fail safely.

## Tasks

### 1. Shared simulation

Files: `src/multibox/simulation.py`, `tests/test_simulation.py`, package metadata.
Interfaces: `World.add_player/remove_player/set_input/step/snapshot/reset_round`;
`Config` tunables, `Input` state; no transport imports.

- [ ] Write behavior tests for balance, spawn/cleanup, packet-independent force,
  jump/contact lifecycle, descending paint, scores/ties, stale input and rounds.
- [ ] Run tests and observe missing-feature failures.
- [ ] Implement the smallest Pymunk world satisfying those tests.
- [ ] Run the simulation suite; commit the tested simulation and dependency pins.

### 2. WebSocket server and lifecycle

Files: `src/multibox/game_server.py`, `src/multibox/protocol.py`,
`tests/test_protocol.py`, `tests/test_server.py`.
Interfaces: `create_app`, `Hub`, latest snapshot queue; protocol version 1 with
join/welcome/input/state messages; authenticated `/admin/round` and metrics.

- [ ] Add failing tests for join/rejoin/duplicate join, strict validation/rate
  bounds, slow sender, complete snapshots, origin restrictions and teacher auth.
- [ ] Implement fixed-deadline stepping, single shared serialization, bounded
  independent senders, expiry, static files and single-process CLI.
- [ ] Run full Python suite; commit tested server/protocol.

### 3. Browser and native clients

Files: `src/multibox/static/*`, `src/multibox/game_client.py`,
`src/multibox/player.py`, `tests/client.test.mjs`, `tests/browser/*`.
Interfaces: full state protocol from task 2; pure URL/input/interpolation helpers.

- [ ] Write failing helper/interaction tests for URL security, key edges,
  interpolation and stale session handling.
- [ ] Build the Canvas UI, clear held input on blur/visibility/disconnect,
  explicit connect and URL switching, touch capture, scores and YOU indicator.
- [ ] Adapt Pygame rendering to the same protocol with optional dependencies.
- [ ] Run helper/browser/native checks, inspect desktop/mobile/crowded captures,
  fix material issues in one batch and commit.

### 4. Classroom delivery and measured capacity

Files: `scripts/load_test.py`, `docs/{protocol,deployment,load-test}.md`,
`STUDY_GUIDE.md`, `README.md`, `Dockerfile`, optional manual Pages workflow, CI.

- [ ] Implement a bounded reproducible active-client harness with simultaneous
  joins, real movement/painting, churn and slow readers; record CPU/RSS/bandwidth,
  tick lag, input-to-snapshot latency and queue bounds.
- [ ] Run 100 active clients then 150 headroom; record actual limits and environment.
- [ ] Write the 120-minute starter tutorial and local/Docker/WSS/Pages instructions.
- [ ] Run full tests, lint, wheel/static packaging and Docker smoke; review the
  branch against the scope; commit and push, open draft PR and verify exact SHA CI.

## Execution record

The user explicitly authorized this implementation task and its draft PR; the
scope and architecture were supplied in the handoff. Execute without another
design/plan approval round or additional execution tasks. Self-review is required
because the handoff prohibits additional allowance tasks.
