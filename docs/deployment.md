# Run locally, prepare a shared server, optionally host the client

Nothing in the PR publishes Pages or changes university infrastructure. Choose
and rehearse the desired setup before class; the same static files serve each.

## Local tutorial: HTTP + same-origin WebSocket

```sh
python -m pip install -c requirements.lock -e .
python -m multibox.game_server
```

Open **http://localhost:8000**. The client defaults to
`ws://localhost:8000/ws`; use Connect explicitly. A local HTTP page can reliably
exercise a local WS server without mixed-content workarounds. A saved Server URL
can be edited back to the local address. Server changes disconnect the old session.

## Docker

```sh
docker build -t multiboxes .
docker run --rm --name multiboxes -p 127.0.0.1:8000:8000 multiboxes
```

The image installs pinned runtime dependencies, includes the static files, runs as
UID 10001 and starts **one** worker/world. It has no Pygame display requirement.
For a managed environment using an HTTPS inspection proxy, preserve its Docker
proxy settings and supply the trusted combined CA during the build:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t multiboxes .
```

That build-only secret is not copied into the image. Keep TLS verification enabled.
For a deliberately campus-reachable HTTP service, the operator can bind the host's
approved interface/port instead of the loopback mapping after their normal network
review. This document does not alter firewalls, university settings or credentials.

## PolyU shared world

An operator can run Python directly with:

```sh
python -m multibox.game_server --host 0.0.0.0 --port 8000 --max-players 160 --round-seconds 180
```

Use the actual approved hostname/IP and port supplied by the teacher; this repo
contains no assumed PolyU address. For the same-origin HTTP client, students visit
`http://<approved-address>:8000/` on the permitted campus network. Rehearse client
isolation, routing, available bandwidth and simultaneous connections on campus Wi-Fi.

Run one process, one container, one Uvicorn worker. Do not add `--workers`, multiple
replicas or a process manager that starts independent worlds. A restart loses the
in-memory round and temporary identities. There is no persistent student data or
DB write in the physics loop. Uvicorn access logging is disabled; production
reverse-proxy logs remain the operator's separate responsibility.

## Hosted HTTPS client: Pages → WSS

A Pages deployment hosts only `src/multibox/static/`. Python remains on the shared
server. The client accepts a full URL such as **`wss://game.example.edu/ws`**, or a
port and custom proxy path such as `wss://game.example.edu:8443/class/ws`. The
reverse proxy must map that path to this app's `/ws` and support WebSocket Upgrade.
The app never fetches or relays the student's configured URL.

An operator must provision a valid TLS certificate and DNS name (or another valid
certified endpoint), route WSS to the single Python process, and explicitly allow
the browser client origin, for example:

```sh
MULTIBOX_ALLOWED_ORIGINS=https://venetanji.github.io python -m multibox.game_server --host 127.0.0.1
```

These are illustrative hostnames, not a claim that any IP has TLS. Preserve the
request Host when proxying; same-origin clients are allowed automatically. Multiple
external origins are comma-separated exact origins, without paths or wildcards.
A reverse proxy should enforce appropriate connection/body limits as well. Native
clients may omit Origin; it is a browser cross-origin guard, not player authentication.

**HTTPS → insecure WS is not a supported hosted mode.** Browser mixed-content and
local-network rules can block or permission-restrict access to local/private
addresses. The UI rejects `ws://` from HTTPS and explains the local HTTP alternative.
Do not disable browser security, ignore certificate errors or assume arbitrary
campus IPs support WSS. See [MDN WebSocket client security guidance](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications#security_considerations).

The optional `.github/workflows/pages.yml` is **workflow_dispatch only**. After
review/merge and an operator's decision to publish, they may select GitHub Actions
as the Pages source and run it manually. It uploads only the static client. It
never runs on pushes or PRs. This task does not enable Pages, dispatch the workflow,
change environments/settings, provision TLS, or deploy a server.

## Teacher start/reset and metrics

Without `MULTIBOX_TEACHER_TOKEN`, admin endpoints return 404. Set a strong random
value in the server process environment through the operator's usual secret
mechanism. Keep it out of static files, URLs, notebooks shared with students and
git. On Windows, set environment variables using PowerShell syntax.

From the operator's machine/process, over localhost or HTTPS:

```sh
curl -X POST http://localhost:8000/admin/round \
  -H "Authorization: Bearer $MULTIBOX_TEACHER_TOKEN" \
  -H 'Content-Type: application/json' -d '{"action":"start"}'
curl http://localhost:8000/admin/metrics \
  -H "Authorization: Bearer $MULTIBOX_TEACHER_TOKEN"
```

`start` clears paint and begins a new round; `reset` clears paint and waits. Bodies
stay in place and held input is cleared. Player WebSockets have no admin command.
Use metrics to check tick lag, discarded catch-up, CPU/RSS externally and bandwidth.
[Load results](load-test.md) give a local baseline, not a campus capacity guarantee.
