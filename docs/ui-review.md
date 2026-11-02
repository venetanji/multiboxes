# UI polish and PR #3 review — 2026-11-02

The browser now carries the approved square-weave reference through setup, play,
settings and recovery. Desktop play hides touch arrows. Portrait uses a directional cross below a full-width framed arena; short landscape
moves the cross beside it. Settings uses a compact labeled icon. The
1200×720 world, fixed-step physics, 100ms interpolation and protocol v2 are unchanged.

The reference was Library `libfile_63f50ba111608191b772affa8ff80d9b`, version 3,
backing file `file_000000009ae081fd85da8f58c7db63d0`: 40,844 bytes, materialized
unchanged and rendered before implementation. Its two 6px orthogonal bands, 24px
band width, 2px crossing clearances and square elbows are adapted in `boundary.mjs`.
Following the latest user correction, the decoration is rendered once on a separate
1248×768 frame **outside** the unchanged 1200×720 gameplay canvas. Even lane-exchange
counts preserve continuous corners. Players are clipped by the inner canvas and
cannot overlap the braid. No fixture players, static scores or mock transport were
copied into production. The original Library item is unchanged.

## Verified behavior

- Setup has labeled fields, clear connection/cancel/error states and a usable
  reconnect path. Browser connection-constructor denial is handled too.
- Settings is modal, releases input, preserves normal text editing, and restores
  canvas focus on Resume/Escape. It explains that the shared world keeps moving
  and edited names apply on reconnect. Disconnect resets stale scores/timer.
- Keyboard control works immediately after Connect, settings/resume and reconnect,
  including while the Settings button has focus. Blur, hidden tabs and resize or
  rotation release input; OS repeats do not invent a fresh jump.
- Real Chromium multi-touch events cover simultaneous right+jump and right+down,
  two fingers on the same button, release of just one finger, touch cancellation,
  and dragging outside a captured button. Pressed feedback follows all held sources.
- The whole canvas keeps 5:3 and all four external boundary corners stay visible. Portrait uses the full available
  width and the touch arrows form a cross in either orientation. Touch
  targets are at least 48 CSS pixels. A 320×480 content-overlap regression now
  checks the actual game-info bounds against the control deck.
- Waiting/round results stay visible during play. Unchanged live-region text is
  not rewritten on each snapshot. Focus indicators and reduced-motion behavior
  remain available.

## Checks and evidence

| Check | Result |
| --- | --- |
| Python 3.12 / SDL dummy | 87 passed |
| Node helper and cross-language wire tests | 8 passed |
| Ruff | Passed |
| Chromium browser suite | 23 passed; 1 optional latency diagnostic skipped |
| Browser security | Non-root UID 1000, namespace and Seccomp-BPF sandboxes enabled; no privileged container |
| Wheel | All 6 static assets byte-identical to source |
| Docker | Build passed; UID 10001 runtime, `/health` and all 6 static assets passed |
| 100 real networked players | Desktop and touch portrait captures; stable joins and inputs |

Inspected viewport sizes: 1440×900 and crowded 1440×1120 desktop; 1000×480 short
desktop; 390×844, 320×568 and 320×480 portrait; 844×390, 568×320 and 480×240
landscape, including rotation. Setup, play, settings, disconnect, error and reconnect
were exercised throughout. No uncaught page errors occurred in those flows.

After all 100 clients joined, a separate bounded rendering sample measured callback
work at p50 **0.5ms desktop / 0.5ms portrait**, p95 **1.4ms / 1.4ms**, over 186/190
frames. These are local JavaScript callback timings, not total GPU time, physical
phone performance or input-to-visible latency. [Raw samples summary](screenshots/desktop-render.json),
[portrait summary](screenshots/mobile-render.json), [layout geometry](screenshots/layouts.json).
The existing [120-second 100/150-client capacity evidence](load-test.md) remains
the server baseline; no server or transport change warranted repeating it. No
remote-lag fix is claimed.

Screenshots from the real app:

- [Desktop, 100 players](screenshots/desktop-100.png)
- [Portrait, 100 players](screenshots/portrait-100.png)
- [Landscape controls](screenshots/landscape.png)
- [320×480 portrait](screenshots/short-portrait.png)
- [Setup](screenshots/setup.png)
- [Settings](screenshots/settings.png)

## Whole-PR review

Reviewed the complete PR against `main` at `5d899a2afa406dfae6e5b69d26406295cfd28a28`,
including the prior `5094545cec6cea2e48f90355e8ead1afc93e7328` implementation and
this polish and subsequent directional-control/external-frame corrections. This was an inline review in the authorized session, not an independent
reviewer or a formal GitHub Approve review. No additional allowance job was launched.

The review covered simulation/contact recharge and paint authority; strict input
validation and sequence bounds; Python/JS binary offsets, numeric bounds, padding
and complete roster/grid checks; uint64 metadata revisions and safe slot reuse;
metadata-before-frame ordering under queue replacement; bounded send/expiry cleanup;
late-session browser events, native rendering, packaging, CI and documentation.
Cross-language golden vectors and lifecycle tests support the protocol conclusions.
The paired ping/firewall/HTTP guide and Docker exercise are preserved. The Pages
workflow remains manual only and was not dispatched.

Concrete findings resolved: desktop toolbar and aspect-ratio layout, resize-held
input, multi-finger pressed feedback, synchronous connection denial, hidden round
results/repeated announcements, compact-portrait content overlap, and 16px editable text to avoid mobile focus zoom. No remaining
merge-blocking findings. No infrastructure, release, registry or security-setting
changes are part of this work.

Limits: headless Chromium emulates phone/touch viewports; hidden-tab handling uses a
controlled hidden observation. Physical iOS/Android browser chrome, real notches,
screen readers, low-powered phones and campus Wi-Fi/TLS routing still need device
or classroom rehearsal. The original Python/Pymunk capacity figures are local
measurements, not a guaranteed classroom size.
