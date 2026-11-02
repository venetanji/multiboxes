# Load results: preserved JSON baseline and packed protocol v2

**The table below is the preserved protocol-v1 JSON baseline at `cbb7a060`.**
Protocol-v2 binary measurements are being added below after the comparable runs;
the binary byte budget in the protocol reference is arithmetic, not measurement.

Measured 2026-11-02 in a separate Multiboxes checkout, using the original JSON authoritative
server and `scripts/load_test.py`. No Alive app/fixtures or campus server was used.
The browser suite was stopped during capacity measurement.

## Environment and workload

Linux 6.18.57 x86-64 / glibc 2.41, Python 3.12.14, AMD EPYC 9V74, five visible
logical CPUs, cgroup quota **4 CPU cores**, memory limit **16 GiB**. One server
process and a separate load-generator process shared this machine. Pymunk 7.1.0,
FastAPI 0.162.0, Starlette 1.10.0, Uvicorn 0.35.0, WebSockets 15.0.1. Loopback TCP,
no TLS or WebSocket compression. CPU percentages below use psutil's convention:
100% is one logical core, not the whole machine.

Each run has simultaneous joins, five seconds of warmup and **120 seconds of
measurement**. All players actively move left/right, request fresh jumps on
support, and use down-force, sending held input at 10 Hz. All clients moved;
server jump/paint counters and changing snapshots confirm actual gameplay.
Five clients read only one state every two seconds with small receive buffers;
they continue sending input and reconnect after slow-consumer closure. Twice per
run, 10% of normal clients deliberately reconnect. These are not idle-socket tests.

## Results

| Measurement | 100 clients (95 normal + 5 slow) | 150 clients (145 normal + 5 slow) |
| --- | ---: | ---: |
| Measured duration | 120.14 s | 120.20 s |
| Physics step rate | 60.003 Hz | 60.006 Hz |
| Normal client snapshot rate, median | 20.001 Hz | 19.999 Hz |
| Input → acknowledged snapshot p50 / p95 / p99 | 30.3 / 57.4 / 61.7 ms | 32.0 / 69.5 / 74.8 ms |
| Worst observed input → snapshot | 73.0 ms | 88.0 ms |
| Tick scheduling lag p95 / p99 / max | 1.89 / 2.09 / 13.25 ms | 1.72 / 2.07 / 15.26 ms |
| Physics work p95 / p99 | 1.89 / 2.37 ms | 3.16 / 4.27 ms |
| Discarded catch-up time | 0 s | 0 s |
| Maximum queued state per client | 1 | 1 |
| Older queued full snapshots replaced | 380 | 342 |
| Slow-consumer closures (expected) | 20 | 18 |
| Unexpected normal-client disconnects | 0 | 0 |
| Connections including deliberate/slow rejoins | 138 | 195 |
| Server CPU median / p95 | 19.0% / 21.9% | 29.0% / 32.2% |
| Generator CPU median / p95 | 23.0% / 27.0% | 48.0% / 51.9% |
| Server RSS start / end / peak | 46.12 / 48.72 / 48.72 MiB | 48.00 / 50.43 / 50.43 MiB |
| Server JSON payload egress | 116.4 Mbit/s | 244.4 Mbit/s |
| Bodies/sessions after client teardown | 0 / 0 | 0 / 0 |

The bounded harness checks passed at both sizes: movement, jumping, paint,
connection stability, ≥59 physics Hz, median ≥19 state Hz, p95 acknowledgement
<150ms, one queued snapshot, complete cleanup. Each run retained over 100,000
normal-client latency samples. Full numeric records and one-second CPU/RSS samples:
[100-client JSON](benchmarks/2026-11-02-100.json),
[150-client JSON](benchmarks/2026-11-02-150.json).

Timing distributions in server metrics retain up to the last 7200 physics ticks;
for these runs that is about the final 120 seconds. Input acknowledgement timing
is measured by the generator's monotonic clock when a snapshot includes its
sequence. It includes batching, parsing and local scheduling, **not** browser
rendering's roughly 100ms interpolation buffer, campus Wi-Fi, TLS or human-device
input delay. Bandwidth counts JSON payload successfully passed to transports;
TCP/WebSocket/TLS/Wi-Fi overhead is additional. Slow readers consume less than the
server attempts to send.

## Other verification

Python simulation/protocol/HTTP/WebSocket/native tests cover balanced teams,
non-overlapping spawns, force independent of packet rate, supporting jump recharge
and no original-contact reuse/held repeats/side-wall flight, down-force,
descending paint and deterministic scoring, expiry, duplicate joins, validation,
complete reconnect/reset snapshots, bounded queues/slow sender and teacher auth.
Native tests use real SDL dummy rendering and a real local WebSocket connection,
including very short jump presses and focus-loss release.

Browser checks run Chromium 141 through pinned Playwright 1.56.1 in non-root Docker
with namespace and seccomp sandbox layers verified at `chrome://sandbox`. They
exercise keyboard/jump, blur/form focus, pointer capture, touch activation, server
switching and late events, outgoing backpressure, unavailable endpoints, and
100-square desktop/mobile views. The same files are packaged for Python and Pages.
Screenshots are visual evidence, not capacity results.

## Reproduce and interpret

```sh
python -m pip install -c requirements.lock -e '.[test,native]'
python scripts/load_test.py --clients 100 --seconds 120 --slow 5 --output /tmp/load-100.json
python scripts/load_test.py --clients 150 --seconds 120 --slow 5 --output /tmp/load-150.json
npm ci --prefix tests/browser
MULTIBOX_PYTHON=python scripts/browser_check.sh /tmp/multibox-browser
```

The load harness starts only a new local server, uses an ephemeral teacher token
for metrics, bounds itself to 150 clients and 300 seconds, and tears down that
process. Do not point it at the live class. A longer soak can reveal issues a
120-second run cannot; small bounded RSS growth here is not proof of no leak.

**Unverified:** actual campus Wi-Fi contention/client isolation, PolyU endpoint
routing/certificates, physical touch devices, low-powered student renderers,
TLS/reverse-proxy overhead and internet-hosted Pages → campus WSS reachability.
The measured JSON bandwidth is material: 150 clients need about 244 Mbit/s of
server egress before framing/TLS, with much of the traffic traversing campus Wi-Fi.
Use the 50–100-student target as a rehearsal starting point, not an attendance
promise. If bandwidth is the bottleneck, try the already-supported 10Hz snapshots
(`Config.snapshot_hz`) and remeasure; correctness remains protected by full states.
Do not scale by starting independent worker worlds.
