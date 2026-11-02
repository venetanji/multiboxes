import { FrameDecoder } from "../../src/multibox/static/wire.mjs";
import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

async function connected(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#status")).toContainText("Connected ·");
}

test("namespace and seccomp browser sandbox are enabled", async ({ page }) => {
  await page.goto("chrome://sandbox");
  const text = await page.locator("body").innerText();
  expect(text).toMatch(/Namespace Sandbox\s+Yes|Layer 1 Sandbox\s+Namespace/);
  expect(text).toMatch(/Seccomp-BPF sandbox\s+Yes/);
  console.log(text);
});

test("unavailable server never reports a successful join", async ({ page }) => {
  await page.goto("/");
  await page.locator("#server").fill("ws://127.0.0.1:9/ws");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#status")).toContainText(
    /Could not connect|Connection closed/,
  );
  await expect(page.locator("#empty")).toBeVisible();
  await expect(page.locator("#population")).toHaveText("0 players connected");
});

test("keyboard, supporting jump, blur and touch capture send authoritative inputs", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({ baseURL, hasTouch: true });
  const page = await context.newPage();
  const sent = [],
    states = [];
  page.on("websocket", (ws) => {
    ws.on("framesent", (frame) => {
      try {
        sent.push(JSON.parse(frame.payload));
      } catch {}
    });
    const decoder = new FrameDecoder();
    ws.on("framereceived", (frame) => {
      try {
        if (typeof frame.payload === "string") {
          const m = JSON.parse(frame.payload);
          if (m.type === "metadata") decoder.metadata(m);
        } else {
          const state = decoder.frame(frame.payload);
          if (state) states.push(state);
        }
      } catch {}
    });
  });
  await connected(page);
  await expect(page.locator("#you")).toContainText("YOU ·");
  await page.keyboard.down("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  await page.waitForTimeout(200);
  await page.keyboard.up("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(false);
  await expect(page.locator("#you")).toContainText("jump ready", {
    timeout: 5000,
  });
  await page.keyboard.down("ArrowUp");
  await expect
    .poll(() => states.at(-1)?.players?.some((p) => p[6] < -100))
    .toBe(true);
  await page.keyboard.up("ArrowUp");
  await page.keyboard.down("ArrowLeft");
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect.poll(() => sent.at(-1)?.left).toBe(false);
  await page.keyboard.up("ArrowLeft");
  const right = page.getByRole("button", { name: "Move right", exact: true });
  await right.scrollIntoViewIfNeeded();
  const box = await right.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  await page.mouse.move(1, 1);
  await page.mouse.up();
  await expect.poll(() => sent.at(-1)?.right).toBe(false);
  await page.getByRole("button", { name: "Settings / disconnect" }).click();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.locator("#empty")).toBeVisible();
  await context.close();
});

test("URL change closes old session, explicit reconnect replaces identity and ignores late events", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const Original = window.WebSocket;
    window.testSockets = [];
    window.WebSocket = class extends Original {
      constructor(...args) {
        super(...args);
        window.testSockets.push(this);
      }
    };
  });
  await connected(page);
  const url = new URL(page.url());
  url.port = process.env.MULTIBOX_SECOND_PORT || "8001";
  url.protocol = "ws:";
  url.pathname = "/ws";
  await page.getByRole("button", { name: "Settings / disconnect" }).click();
  await page.locator("#server").fill(url.href);
  await expect(page.locator("#status")).toContainText("Server changed");
  await expect(page.locator("#empty")).toBeVisible();
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#status")).toContainText("Connected ·");
  await page.evaluate(() =>
    window.testSockets[0].onmessage({
      data: '{"type":"bad-old-server-event"}',
    }),
  );
  await expect(page.locator("#status")).toContainText("Connected ·");
});

test("a full outgoing browser buffer disconnects cleanly without recursion", async ({
  page,
}) => {
  await connected(page);
  await page.evaluate(() =>
    Object.defineProperty(WebSocket.prototype, "bufferedAmount", {
      get: () => 4096,
      configurable: true,
    }),
  );
  await expect(page.locator("#status")).toContainText(
    "Connection is too slow",
    { timeout: 2500 },
  );
  await expect(page.locator("#empty")).toBeVisible();
});

test("focused form clears gameplay keys even if release happens inside the input", async ({
  page,
}) => {
  const sent = [];
  page.on("websocket", (ws) =>
    ws.on("framesent", (frame) => {
      try {
        sent.push(JSON.parse(frame.payload));
      } catch {}
    }),
  );
  await connected(page);
  await page.keyboard.down("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(true);
  await page.getByRole("button", { name: "Settings / disconnect" }).click();
  await page.locator("#nickname").focus();
  await page.keyboard.up("ArrowRight");
  await expect.poll(() => sent.at(-1)?.right).toBe(false);
});

test("crowded desktop and touch mobile show the local square and fit the viewport", async ({
  browser,
  baseURL,
}) => {
  for (const [name, viewport, hasTouch] of [
    ["desktop", { width: 1440, height: 1120 }, false],
    ["mobile", { width: 390, height: 844 }, true],
  ]) {
    const context = await browser.newContext({
      viewport,
      hasTouch,
      isMobile: hasTouch,
    });
    await context.addInitScript(() => {
      const original = requestAnimationFrame;
      window.renderSamples = [];
      window.requestAnimationFrame = (callback) =>
        original((time) => {
          const start = performance.now();
          callback(time);
          window.renderSamples.push(performance.now() - start);
          if (window.renderSamples.length > 600) window.renderSamples.shift();
        });
    });
    const page = await context.newPage();
    await page.goto(baseURL);
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#status")).toContainText("Connected ·");
    await page.evaluate(() => {
      window.bots = Array.from({ length: 99 }, (_, i) => {
        const ws = new WebSocket(document.getElementById("server").value);
        let seq = 0;
        ws.onopen = () =>
          ws.send(JSON.stringify({ type: "join", v: 2, nickname: `box ${i}` }));
        ws.onmessage = (event) => {
          if (typeof event.data !== "string") return;
          const m = JSON.parse(event.data);
          if (m.type === "welcome") {
            ws.timer = setInterval(() => {
              if (ws.readyState === 1)
                ws.send(
                  JSON.stringify({
                    type: "input",
                    seq: seq++,
                    left: i % 2 === 0,
                    right: i % 2 === 1,
                    jump: seq % 20 < 2,
                    down: seq % 30 < 12,
                  }),
                );
            }, 50);
          }
        };
        return ws;
      });
    });
    await expect(page.locator("#population")).toHaveText(
      "100 players connected",
      { timeout: 15000 },
    );
    await page.evaluate(() => {
      window.renderSamples.length = 0;
    });
    await page.waitForTimeout(3000);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator("#you")).toContainText("YOU ·");
    if (hasTouch) {
      await page.getByRole("button", { name: "Jump", exact: true }).tap();
    }
    if (process.env.MULTIBOX_QA_DIR)
      await page.screenshot({
        path: `${process.env.MULTIBOX_QA_DIR}/${name}.png`,
        fullPage: true,
      });
    if (process.env.MULTIBOX_QA_DIR) {
      const samples = await page.evaluate(() => window.renderSamples);
      samples.sort((a, b) => a - b);
      await writeFile(
        `${process.env.MULTIBOX_QA_DIR}/${name}-render.json`,
        JSON.stringify(
          {
            players: 100,
            samples: samples.length,
            p50_ms: samples[Math.floor(samples.length * 0.5)],
            p95_ms: samples[Math.floor(samples.length * 0.95)],
            max_ms: samples.at(-1),
          },
          null,
          2,
        ),
      );
    }
    await page.evaluate(() =>
      window.bots.forEach((ws) => {
        clearInterval(ws.timer);
        ws.close();
      }),
    );
    await context.close();
  }
});

test("OS key repeat after blur cannot rearm a held jump", async ({ page }) => {
  const sent = [];
  page.on("websocket", (ws) =>
    ws.on("framesent", (frame) => {
      try {
        sent.push(JSON.parse(frame.payload));
      } catch {}
    }),
  );
  await connected(page);
  await page.keyboard.down("ArrowUp");
  await expect.poll(() => sent.at(-1)?.jump).toBe(true);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect.poll(() => sent.at(-1)?.jump).toBe(false);
  await page.keyboard.down("ArrowUp");
  await page.waitForTimeout(100);
  expect(sent.at(-1)?.jump).toBe(false);
  await page.keyboard.up("ArrowUp");
});
