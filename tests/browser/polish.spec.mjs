import { test, expect } from "@playwright/test";

async function join(page) {
  const sent = [];
  page.on("websocket", (ws) =>
    ws.on("framesent", ({ payload }) => {
      try {
        sent.push(JSON.parse(payload));
      } catch {}
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#world")).toBeFocused();
  return sent;
}

async function fits(page) {
  const box = await page.locator("#world").boundingBox();
  const viewport = page.viewportSize();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
  expect(box.width / box.height).toBeCloseTo(5 / 3, 2);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollHeight <= innerHeight &&
        document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

test("desktop keeps the entire woven world visible without a touch toolbar", async ({
  page,
}) => {
  await join(page);
  await expect(page.locator(".touch-controls")).toBeHidden();
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1000, height: 480 },
    { width: 480, height: 240 },
  ]) {
    await page.setViewportSize(viewport);
    await fits(page);
  }
  const pixels = await page.locator("#boundary").evaluate((canvas) => {
    const ctx = canvas.getContext("2d");
    return [
      [6, 6],
      [1242, 6],
      [1242, 762],
      [6, 762],
    ].map(([x, y]) => [...ctx.getImageData(x, y, 1, 1).data]);
  });
  expect(pixels).toEqual(Array(4).fill([32, 35, 31, 255]));
});

test("resizing releases held input before a control or orientation moves", async ({
  page,
}) => {
  const sent = await join(page);
  await page.keyboard.down("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  await page.setViewportSize({ width: 900, height: 500 });
  await expect.poll(() => sent.at(-1)?.right).toBe(false);
  await page.keyboard.up("ArrowRight");
});

test("hidden tab releases input and requires a fresh press on return", async ({
  page,
}) => {
  const sent = await join(page);
  await page.keyboard.down("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  // Chromium headless does not hide pages when another tab is brought forward.
  // Exercise the real visibility handler with the browser's hidden observation.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => sent.at(-1)?.right).toBe(false);
  await page.evaluate(() => {
    delete document.hidden;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.keyboard.down("ArrowRight");
  await page.waitForTimeout(100);
  expect(sent.at(-1)?.right).toBe(false);
  await page.keyboard.up("ArrowRight");
  await page.keyboard.down("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  await page.keyboard.up("ArrowRight");
});

test("a constructor denial is recoverable", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    window.RealWebSocket = WebSocket;
    window.WebSocket = class {
      constructor() {
        throw new DOMException("Network permission denied", "SecurityError");
      }
    };
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#status")).toHaveAttribute("data-error", "true");
  await expect(
    page.getByRole("button", { name: "Connect", exact: true }),
  ).toBeEnabled();
  await page.evaluate(() => {
    window.WebSocket = window.RealWebSocket;
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#world")).toBeFocused();
});

test("pending connection can be canceled without a late successful join", async ({
  page,
}) => {
  await page.routeWebSocket("**/ws", () => {});
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connecting…", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Cancel connection", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Connect", exact: true }),
  ).toBeEnabled();
  await expect(page.locator("#empty")).toBeVisible();
});

test("waiting and round results remain visible outside settings", async ({
  page,
  request,
  baseURL,
}) => {
  const url = new URL(baseURL);
  url.port = "8002";
  const admin = `${url.origin}/admin/round`;
  const headers = { Authorization: "Bearer browser-qa-only" };
  expect(
    (await request.post(admin, { headers, data: { action: "reset" } })).ok(),
  ).toBe(true);
  await page.goto(url.origin);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#round-status")).toBeVisible();
  await expect(page.locator("#round-status")).toContainText(
    "Waiting for the teacher",
  );
  await page.evaluate(() => {
    window.roundAnnouncements = 0;
    new MutationObserver(() => window.roundAnnouncements++).observe(
      document.getElementById("round-status"),
      { childList: true },
    );
  });
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => window.roundAnnouncements)).toBe(0);
  expect(
    (await request.post(admin, { headers, data: { action: "start" } })).ok(),
  ).toBe(true);
  await expect(page.locator("#round-status")).toBeHidden();
  await expect(page.locator("#round-status")).toContainText(/wins|draw/);
  await expect(page.locator("#round-status")).toBeVisible();
});

test.describe("touch controls", () => {
  test.use({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  });

  test("portrait and landscape fit four generous controls and an intact arena", async ({
    page,
  }) => {
    await join(page);
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 320, height: 568 },
      { width: 320, height: 480 },
      { width: 844, height: 390 },
      { width: 568, height: 320 },
      { width: 480, height: 240 },
    ]) {
      await page.setViewportSize(viewport);
      await fits(page);
      const settings = await page.locator("#open-settings").boundingBox();
      expect(settings.x + settings.width).toBeLessThanOrEqual(viewport.width);
      await expect(page.locator(".touch-controls")).toBeVisible();
      if (viewport.height > viewport.width) {
        const game = await page.locator(".game-info").boundingBox();
        const deck = await page.locator(".touch-controls").boundingBox();
        expect(game.y + game.height).toBeLessThanOrEqual(deck.y + 1);
        const frame = await page.locator(".world-frame").boundingBox();
        expect(frame.width).toBeCloseTo(viewport.width, 0);
      }
      for (const button of await page.locator("[data-control]").all()) {
        const box = await button.boundingBox();
        expect(box.width).toBeGreaterThanOrEqual(48);
        expect(box.height).toBeGreaterThanOrEqual(48);
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
      }
    }
  });

  test("arrows form a cross and the braid sits strictly outside the playable canvas", async ({
    page,
  }) => {
    await join(page);
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 320, height: 480 },
      { width: 844, height: 390 },
      { width: 480, height: 240 },
    ]) {
      await page.setViewportSize(viewport);
      const centre = async (key) => {
        const b = await page.locator(`[data-control=${key}]`).boundingBox();
        return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
      };
      const [up, down, left, right] = await Promise.all([
        centre("jump"),
        centre("down"),
        centre("left"),
        centre("right"),
      ]);
      expect(up.x).toBeCloseTo(down.x, 0);
      expect(left.y).toBeCloseTo(right.y, 0);
      expect(up.y).toBeLessThan(left.y);
      expect(down.y).toBeGreaterThan(left.y);
      expect(left.x).toBeLessThan(up.x);
      expect(right.x).toBeGreaterThan(up.x);
      const world = await page.locator("#world").boundingBox(),
        frame = await page.locator("#boundary").boundingBox();
      expect(world.x).toBeGreaterThan(frame.x);
      expect(world.y).toBeGreaterThan(frame.y);
      expect(world.x + world.width).toBeLessThan(frame.x + frame.width);
      expect(world.y + world.height).toBeLessThan(frame.y + frame.height);
      await fits(page);
    }
  });

  test("multiple real fingers retain independent movement, jump and pressed feedback", async ({
    page,
  }) => {
    const sent = await join(page);
    const cdp = await page.context().newCDPSession(page);
    const point = async (control, id, dx = 0) => {
      const box = await page.locator(`[data-control=${control}]`).boundingBox();
      return { x: box.x + box.width / 2 + dx, y: box.y + box.height / 2, id };
    };
    const right1 = await point("right", 1, -8),
      right2 = await point("right", 2, 8),
      jump = await point("jump", 3);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [right1],
    });
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [right1, right2, jump],
    });
    await expect.poll(() => sent.at(-1)?.right && sent.at(-1)?.jump).toBe(true);
    // CDP touchEnd lists the contacts to release, not those remaining.
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [right1],
    });
    await expect(page.locator("[data-control=right]")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect.poll(() => sent.at(-1)?.right && sent.at(-1)?.jump).toBe(true);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchCancel",
      touchPoints: [],
    });
    await expect
      .poll(() => sent.at(-1)?.right || sent.at(-1)?.jump)
      .toBe(false);
    const down = await point("down", 4);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [right1, down],
    });
    await expect.poll(() => sent.at(-1)?.right && sent.at(-1)?.down).toBe(true);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ ...right1, x: 1, y: 1 }, down],
    });
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    await expect
      .poll(() => sent.at(-1)?.right || sent.at(-1)?.down)
      .toBe(false);
  });
});
