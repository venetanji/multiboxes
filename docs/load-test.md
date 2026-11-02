# Load results: complete binary snapshots versus JSON baseline

Protocol v2 reduced measured server payload by **75.6% at 100 players**
and **75.6% at 150**, using the comparable nominal-10 Hz input
workload. Physics and snapshot targets stayed 60/ 20 Hz. Additional runs use the
browser's 20 Hz heartbeat cadence. These are loopback measurements, not Wi-Fi or
remote-route measurements, and do not establish the cause of transient remote lag.

## Before and after

| Nominal input workload | Players | JSON v1 payload | Packed v2 payload |                Reduction |
| ---------------------- | ------: | --------------: | ----------------: | -----------------------: |
| 10 Hz comparison        |     100 |  116.415 Mbit/s |     28.413 Mbit/s |                    75.6% |
| 10 Hz comparison        |     150 |  244.393 Mbit/s |     59.596 Mbit/s |                    75.6% |
| Browser-like 20 Hz      |     100 |    Not measured |     28.433 Mbit/s | No matched JSON baseline |
| Browser-like 20 Hz      |     150 |    Not measured |     59.593 Mbit/s | No matched JSON baseline |

The original [100-client JSON record](benchmarks/2026-11-02-100.json) and
[150-client JSON record](benchmarks/2026-11-02-150.json) at `cbb7a060` are preserved.
Their 120.14/120.20s runs had input-to-snapshot p95 57.4/69.5ms, median server CPU
19%/29%, RSS peak 48.72/50.43MiB, no unexpected normal-client drops and queue maximum 1.
The new protocol does **not** show an acknowledgement-latency improvement; packing
primarily saves bandwidth. The Python load generator spends more CPU unpacking
numeric records than its old C-backed JSON parser. Server CPU stayed similar at
the comparison workload and rises modestly with the actual 20 Hz input workload.

## What bytes changed (arithmetic, not a benchmark)

In illustrative one-second simulation samples with `bot N` nicknames, player rows
were 5597 of 7278 JSON bytes at 100 players and 8457 of 10138 at 150; paint was 1502 bytes
including JSON quotes in each. Repeated identities/nicknames and textual numeric
motion dominate. Packing only paint would leave most of the traffic unchanged.

V2 uses a 40-byte header, **14 bytes/player**, and a 375-byte default two-bit paint
array. Names/constants are in reliable complete revisioned metadata, sent when
needed. This gives **1815 bytes at 100** and **2515 bytes at 150** per complete
gameplay frame. Steady full delivery at 20 Hz would arithmetically be 29.04/60.36 Mbit/s
before metadata/framing. Actual delivery differs because five deliberately slow
readers miss replaced states, players briefly reconnect and metadata is included.
No compression or dependent gameplay deltas are involved. See
[protocol offsets, limits and synchronization](protocol.md).

## Workload and environment

Measured 2026-11-02 in the separate Multiboxes checkout. Linux 6.18.57 x86-64,
glibc 2.41, Python 3.12.14, AMD EPYC 9V74; five visible logical CPUs, cgroup quota
**4 cores**, memory limit **16 GiB**. The single authoritative server and separate
load-generator process share this machine. CPU 100% means one logical core.
Browser tests and Docker builds were stopped during the capacity measurements.

Each run: simultaneous joins, five-second warmup, then 120 seconds of active
left/right movement, fresh supporting jumps, downward force and automatic paint.
Five readers accept one message every two seconds with a small receive buffer;
normal players continue independently. Twice, 10% of normal players reconnect.
All clients moved; paint/jump counters increased. All required checks passed.
These are not idle-socket counts.

For comparability, nominal 10 Hz retains the original work-then-sleep pacing;
observed rates are reported below. The 20 Hz condition uses absolute deadlines,
matching browser heartbeat cadence rather than accumulating work+sleep drift.
Initial under-paced 20 Hz trials were discarded from the comparison and rerun;
final observed medians are essentially 20 Hz. Extra human key-edge bursts remain
subject to the independently tested 60/s rate limit.

All v2 egress totals include binary frames **and JSON metadata/welcome** payloads,
including churn. Baseline metrics counted state JSON only, making the comparison
slightly conservative. TCP/WebSocket/TLS/Wi-Fi overhead is not counted. Consumed
bytes can be lower than transport-sent payload for intentionally slow readers.
Input-to-snapshot uses the generator's monotonic clock when its accepted sequence
appears in a snapshot; it excludes the rendering interpolation buffer and device
input/display delays. Tick metrics retain the latest 7200 samples (about 120 s).

## V2 measured results

| Measurement                              |             100 / 10 Hz |             150 / 10 Hz |             100 / 20 Hz |             150 / 20 Hz |
| ---------------------------------------- | --------------------: | --------------------: | --------------------: | --------------------: |
| Measured seconds                         |                120.16 |                120.28 |                120.16 |                120.29 |
| Physics Hz                               |                60.002 |                60.008 |                60.002 |                60.003 |
| Normal-client snapshot Hz, median        |                19.998 |                20.003 |                19.998 |                20.001 |
| Observed input Hz, median                |                 9.870 |                 9.785 |                19.998 |                20.001 |
| Input → snapshot p50 / p95 / p99 (ms)    |    31.0 / 61.0 / 65.9 |    34.5 / 75.9 / 81.6 |    42.3 / 48.8 / 50.6 |    28.7 / 43.0 / 47.4 |
| Worst observed input → snapshot (ms)     |                  77.3 |                 110.6 |                  72.1 |                 107.6 |
| Server payload Mbit/s                    |                28.413 |                59.596 |                28.433 |                59.593 |
| Server CPU median / p95 (%)              |           19.0 / 21.0 |           29.0 / 32.0 |           21.0 / 24.0 |           33.0 / 39.0 |
| Generator CPU median / p95 (%)           |           29.0 / 32.0 |           60.9 / 65.9 |           31.0 / 35.0 |           64.0 / 71.0 |
| Server RSS start / end / peak (MiB)      | 45.57 / 48.22 / 48.22 | 47.95 / 50.66 / 50.66 | 46.23 / 48.98 / 48.98 | 48.43 / 51.75 / 51.75 |
| Tick scheduling lag p95 / p99 / max (ms) |    1.94 / 2.46 / 5.41 |   1.78 / 2.23 / 27.31 |    1.76 / 2.67 / 8.73 |   1.20 / 2.12 / 35.64 |
| Physics work p95 / p99 (ms)              |           1.91 / 2.50 |           3.17 / 4.32 |           1.87 / 2.54 |           3.60 / 4.26 |
| Discarded catch-up time (s)              |                   0.0 |                   0.0 |                   0.0 |                   0.0 |
| Maximum queued state                     |                     1 |                     1 |                     1 |                     1 |
| Replaced old queued states               |                   380 |                   380 |                   380 |                   380 |
| Slow-consumer closures                   |                    20 |                    20 |                    20 |                    20 |
| Unexpected normal-client disconnects     |                     0 |                     0 |                     0 |                     0 |
| Connections including rejoins            |                   138 |                   198 |                   138 |                   198 |
| Bodies / sessions after teardown         |                 0 / 0 |                 0 / 0 |                 0 / 0 |                 0 / 0 |

Complete numeric records, including per-second CPU/RSS samples and bounded queue
counters: [100 clients / 10 Hz](benchmarks/2026-11-02-v2-100-10hz.json), [150 clients / 10 Hz](benchmarks/2026-11-02-v2-150-10hz.json), [100 clients / 20 Hz](benchmarks/2026-11-02-v2-100-20hz.json), [150 clients / 20 Hz](benchmarks/2026-11-02-v2-150-20hz.json).

## Visual/input verification and limits

87 Python tests and 8 Node tests cover simulation, protocol, native rendering,
full-width bounds, uint64 revisions, shared Python/JS golden vectors, malformed
frames, paint padding/max sizes, slot reuse, stale frames and reliable metadata
when intermediate queued states are replaced. Native clients use real local
WebSocket connections and SDL dummy rendering.

13 sandboxed Chromium checks cover keyboard/touch, blur/text focus, settings and
URL switching, reconnect/disconnect, outgoing backpressure, 100-square desktop/mobile
views and viewport-only play at 1440×900, 390×844, 844×390 and 480×240 including resize.
Actual screenshots were inspected; namespace and seccomp sandbox layers pass.
These are visual/input checks, not 100 physical-device rendering benchmarks.

The original overflowing page/key-focus problem was reproduced and fixed. A small
exploratory local Canvas-pixel probe before the layout fix observed 124.5–159.9ms
from stationary right-key input to first visible motion (8 samples); this is not
an end-to-end remote measurement or a latency improvement claim. Delayed-condition
trials were confounded by residual movement and are excluded. The optional pixel
probe remains off in ordinary CI. Per the user's later clarification that local
play was fine and remote performance had recovered, there is no further transient
lag investigation or WebRTC rewrite. Authoritative interpolation remains roughly
100ms; server acknowledgements alone do not measure input-to-visible-motion.

**Still unverified:** actual campus Wi-Fi contention/isolation, PolyU endpoint and
TLS/certificate/reverse-proxy setup, physical mobile devices, low-powered renderers
and hosted Pages→campus WSS reachability. Neither the old transient remote delay nor
its later recovery was traced to a transport or to bandwidth. Reduced traffic is
useful headroom, not proof of a remote-lag fix or a class-size guarantee. Two-minute
RSS traces are not a long soak or proof of no leak. One process/world remains
required; do not add independent Uvicorn workers to scale.

## Reproduce

```sh
python -m pip install -c requirements.lock -e '.[test,native]'
python scripts/load_test.py --clients 100 --seconds 120 --slow 5 --input-hz 10 --output /tmp/v2-100-10.json
python scripts/load_test.py --clients 150 --seconds 120 --slow 5 --input-hz 10 --output /tmp/v2-150-10.json
python scripts/load_test.py --clients 100 --seconds 120 --slow 5 --input-hz 20 --output /tmp/v2-100-20.json
python scripts/load_test.py --clients 150 --seconds 120 --slow 5 --input-hz 20 --output /tmp/v2-150-20.json
node --test tests/*.test.mjs
npm ci --prefix tests/browser
MULTIBOX_PYTHON=python scripts/browser_check.sh /tmp/multibox-browser
```

The bounded load harness starts a new **local** server with an ephemeral metrics
token, allows at most 150 clients / 300 seconds and tears down only its own process.
It cannot be pointed at the live class. For classroom address/ping/HTTP/firewall
checks and an optional local image build, see [classroom networking](classroom-networking.md).
