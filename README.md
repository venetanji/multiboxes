# Multiboxes · Black / White

A multiplayer physics and territory-painting starter for a two-hour networking
class. Python/Pymunk owns the world; browser Canvas and optional Pygame clients
render the same state. No accounts, database, build tool or JavaScript framework.

Two balanced teams compete for painted coverage. Move left/right, **jump with a
fresh up press**, land on the floor or another square to recharge, then descend to
paint automatically. **Down adds downward force**. Teammates can stack and boost
each other. Your square always has a bright pink outline and **YOU** label.

## Run locally

Python **3.11 or 3.12** is tested. Create and activate a virtual environment:

```sh
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -c requirements.lock -e .
python -m multibox.game_server
```

Open **http://localhost:8000** in two tabs, choose nicknames and click **Connect**.
The client defaults to the same origin's `/ws`. Arrows or WASD work; Space also
jumps. The on-screen buttons support touch and keyboard activation. Connected play fills
the viewport without document scrolling; **Settings** opens connection settings
and Disconnect, and **Resume game** restores canvas focus. The shared landscape
world keeps its aspect ratio, so portrait/short screens can have letterboxing. Input clears
on blur, hidden tabs, form focus and disconnect; stale input also expires at the
server after 0.5 seconds. Reconnect gives a new temporary identity and full state.

The first player starts a three-minute round; results show for ten seconds, then a
new round begins. Coverage percentages include neutral grey area, so BLACK and
WHITE need not sum to 100%. Round start/reset controls require a private teacher
token; they are absent from the student interface.

The launcher still supports `python launcher.py server`, `client` and `test`.
For the native client, first install `python -m pip install -c requirements.lock -e '.[native]'`,
then run `python -m multibox.game_client --server ws://localhost:8000/ws --nickname Box`.

## Shared classroom server / optional Pages client

```sh
python -m multibox.game_server --host 0.0.0.0 --port 8000 --max-players 160 --round-seconds 180
```

Students can use the server's HTTP client on an allowed campus network, or the
**identical static client** can later be hosted on GitHub Pages and configured
with a full server URL, including scheme, hostname/IP, port and path. A URL query
such as `?server=wss%3A%2F%2Fgame.example.edu%2Fws` pre-fills it, but never connects
automatically. Editing the address disconnects the previous session.

**HTTPS Pages requires WSS with a valid certificate/domain.** A university IP does
not imply TLS. For reliable localhost exercises, use the locally served HTTP
client. Do not bypass mixed-content, certificate or local-network permission
checks. Pages serves static files only; Python runs separately. The manual Pages
workflow is prepared but no deployment is automatic.

See [deployment and Docker instructions](docs/deployment.md), including explicit
allowed origins, one-process operation, TLS/reverse-proxy preparation and teacher
controls. No infrastructure or Pages settings are changed by installing this repo.

## Read / change / test

- [120-minute tutorial](STUDY_GUIDE.md): run the supplied starter, inspect messages,
  change a rule, test server authority, reconnect, then join the shared world.
- [`simulation.py`](src/multibox/simulation.py): readable fixed-step Pymunk world
  and `Config` tunables: gravity, acceleration, jump impulse, paint threshold,
  round length and bounded paint-cell size.
- [`game_server.py`](src/multibox/game_server.py): HTTP/WebSocket lifecycle,
  fixed-deadline scheduler, bounded latest-state queues and authenticated metrics.
- [`protocol.py`](src/multibox/protocol.py) / [protocol reference](docs/protocol.md):
  strict input validation and complete authoritative snapshots.
- [`static/`](src/multibox/static): plain HTML/CSS/Canvas, interpolation, URL settings,
  keyboard/touch input and local-player indication. These files are also in wheels.
- [`game_client.py`](src/multibox/game_client.py): optional native Pygame renderer
  using the same WebSocket world. Legacy `avahi_utils.py` is an optional historical
  OSC/Zeroconf helper; it is not imported by the server or browser.

```sh
python -m pip install -c requirements.lock -e '.[test,native]'
python -m pytest -q
ruff check src tests scripts
node --test tests/*.test.mjs
npm ci --prefix tests/browser
# Linux + Docker + a Python 3.12 environment; non-root Chromium with sandbox checks:
MULTIBOX_PYTHON=python scripts/browser_check.sh /tmp/multibox-browser
# Active simulated players, not idle sockets (each starts its own local server):
python scripts/load_test.py --clients 100 --seconds 120 --slow 5 --input-hz 20 --output /tmp/load-100.json
python scripts/load_test.py --clients 150 --seconds 120 --slow 5 --input-hz 20 --output /tmp/load-150.json
```

**Measured payload egress fell from 116.4/244.4 to 28.4/59.6 Mbit/s** at 100/150 active
players in the comparable runs. Additional 20 Hz-heartbeat runs were also checked.
[Full measured results and limitations](docs/load-test.md) distinguish loopback
capacity, browser checks and the still-required campus Wi-Fi/device rehearsal.
Physics targets 60 Hz and full state snapshots 20 Hz; these are targets, not a
promise for arbitrary hardware. Packed complete frames use 14 bytes/player and two-bit paint; reliable versioned
metadata carries names/constants. Each frame is encoded once, shared across
bounded one-packet queues, and each client sends independently with a timeout.
One slow client cannot hold up the world. No database writes occur in physics;
saving final round results is a next-week exercise.

## OSC, UDP and WebSockets

The original project already had a headless Pymunk server with moving bodies,
gravity, walls and collisions, plus Pygame rendering. This adaptation keeps those
ideas and replaces its unbounded per-player/per-client executor sends with one
batched state protocol. Movement now follows held input at fixed physics steps,
rather than force per incoming packet. Native clients remain useful without a
separate simulation.

OSC is a message format often used over UDP. UDP has no connection or guaranteed
ordering/delivery; the old discovery/listener assumptions do not map to a browser.
WebSockets provide bidirectional messages over TCP (WSS adds TLS). Reliable delivery
also means slow readers need explicit backpressure handling. Complete gameplay frames and reliable metadata make
queue replacement and reconnect safe; students do not have to write a networking
engine to change the game.

The [classroom networking guide](docs/classroom-networking.md) includes a short
paired ping/HTTP exercise, firewall and campus-Wi-Fi troubleshooting, and an
optional build-your-own Docker image exercise.
