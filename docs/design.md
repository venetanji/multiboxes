# Browser territory game: approved scope

Adapt the existing headless Pymunk squares, gravity, walls and collisions into a
classroom multiplayer starter. One Python process owns identities, balanced BLACK
and WHITE teams, input, jump recharge, descending paint, scores and short rounds.
The browser draws full authoritative snapshots and interpolates positions. Nicknames
are temporary; there are no accounts or database writes.

The approved approach is FastAPI/asyncio WebSockets with a plain Canvas client.
OSC is a transport rather than a physics requirement. Keeping a separate OSC
simulation would complicate the lesson; the Pygame client will instead share the
WebSocket protocol. Legacy discovery helpers may remain optional, but the old
executor fan-out and packet-frequency-dependent forces must go.

Physics targets 60 fixed steps/second and snapshots target 20/second. Each snapshot
is complete, serialized once, and offered to one bounded latest-state queue per
client. A timed-out sender is disconnected independently. Limits cover sessions,
message size/rate, stale input, inactivity and grid size. Measurements, rather than
these target rates, determine classroom capacity.

Controls: left/right movement; one fresh up/jump press on supporting floor/player
contact; down adds downward force. A used contact cannot recharge another jump
until support has been lost. Painting is automatic only while descending. A
bounded grid uses deterministic last-writer paint ordering. Server-assigned spawns
avoid overlap. The local square has a bright outline, YOU label and spawn marker.

The same static files are served by Python for localhost exercises or can be
manually published to Pages later. The full ws:// or wss:// URL is editable and
requires an explicit Connect action. HTTPS hosting requires a valid WSS endpoint;
no mixed-content workarounds or arbitrary URL relay. Teacher reset/start requires
a server-side bearer token and is absent from the student UI.

The initial delivery was a draft PR. The later approved UI-polish scope includes
review and merge of PR #3 after verification; see the
[UI plan](superpowers/plans/2026-11-02-ui-polish.md). No Alive, teaching or PFAD
changes, deployment, Pages enablement, PolyU infrastructure changes, formal approval
review or release are included.

Validation covers simulation/protocol lifecycle, keyboard/touch/blur/URL switching,
native rendering, sandboxed desktop/mobile screenshots, and bounded active-client
load runs at 100 then 150 clients. Campus Wi-Fi and physical-device rehearsal remain
outside this environment. Include a 120-minute tutorial, Docker/local/PolyU run
instructions, protocol reference, dependency pins and reproducible load evidence.
