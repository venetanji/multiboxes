# Browser checks

`npm ci --prefix tests/browser` installs the pinned Playwright 1.56.1 runner.
Pure helper tests need only `node --test tests/*.test.mjs`.

On Linux, install Python 3.12 dependencies (`pip install -c requirements.lock -e '.[test]'`)
then run `MULTIBOX_PYTHON=python scripts/browser_check.sh /tmp/multibox-browser`.
It mounts this checkout read-only, starts two ephemeral Multiboxes servers inside
the same container, and runs Chromium as the caller's non-root UID with namespace
and seccomp sandboxing. It adds no Docker capabilities and sets no-new-privileges.
The first test verifies `chrome://sandbox`. It never mounts Alive or its fixtures.

The pinned Microsoft Playwright image and Docker seccomp profile were reused from
the environment's proven browser setup. `seccomp.json` is a public syscall policy,
not a credential; it retains Docker's syscall filtering while allowing Chromium
user namespaces. Background and rationale:
[Playwright Docker documentation](https://playwright.dev/docs/docker#recommended-docker-configuration).
`--disable-setuid-sandbox` selects the namespace sandbox; it does not disable the
Chromium sandbox. A missing namespace/seccomp layer fails the test. Do not replace
it with `--no-sandbox` or privileged Docker.

For a conventional local Playwright installation, start servers on 8000 and 8001,
allow `http://localhost:8000` on the second with `MULTIBOX_ALLOWED_ORIGINS`, install
Chromium through Playwright, and run `npm test --prefix tests/browser`. The pinned
container is the tested path here. macOS/Windows host site-packages cannot be
mounted as Linux native dependencies; use native Playwright or a Linux environment.

Checks cover real joins, keyboard/jump/blur, touch pointer capture, failed servers,
URL switching/late old-session events, bounded browser outgoing buffering, and
100-square desktop/mobile captures. Play-mode checks additionally cover viewport
fit at 1440×900, 390×844, 844×390 and 480×240; resize, settings overlay, text editing,
real touch input and restored keyboard focus. An optional `MULTIBOX_LATENCY=1`
diagnostic samples actual Canvas pixels for input-to-visible-motion; it is skipped
in ordinary CI and is not evidence about a remote route. These captures are **visual/interaction**
evidence. Separate 100/150 active-client capacity measurements use
`scripts/load_test.py`, with the browser suite stopped.
