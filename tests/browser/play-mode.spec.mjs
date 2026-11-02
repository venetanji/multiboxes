import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

async function join(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#you")).toContainText("YOU ·");
}

for (const [name, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
  ["landscape", { width: 844, height: 390 }],
  ["short", { width: 480, height: 240 }],
]) {
  test(`play fits ${name}, owns arrows, settings release input and restore focus`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await join(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator("#server")).not.toBeVisible();
    await expect(page.locator("#world")).toBeFocused();
    await page.keyboard.down("ArrowDown");
    await page.waitForTimeout(100);
    await page.keyboard.up("ArrowDown");
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await page.getByRole("button", { name: "Settings / disconnect" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#nickname").focus();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.type("x");
    await page.getByRole("button", { name: "Resume game" }).click();
    await expect(page.locator("#world")).toBeFocused();
    await page.setViewportSize({
      width: viewport.height,
      height: viewport.width,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    await page.setViewportSize(viewport);
    if (process.env.MULTIBOX_QA_DIR)
      await page.screenshot({
        path: `${process.env.MULTIBOX_QA_DIR}/play-${name}.png`,
      });
    await page.getByRole("button", { name: "Settings / disconnect" }).click();
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(page.locator("#server")).toBeVisible();
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#world")).toBeFocused();
  });
}

test("measure key to actual Canvas motion locally and with 60ms delay each way", async ({
  browser,
  baseURL,
}) => {
  test.skip(
    !process.env.MULTIBOX_LATENCY,
    "Optional diagnostic; remote lag is not reproduced by localhost.",
  );
  test.setTimeout(60000);
  const results = [];
  for (const delay of [0, 60]) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
    });
    await context.addInitScript((delay) => {
      if (!delay) return;
      const Original = WebSocket;
      window.WebSocket = class extends Original {
        constructor(...args) {
          super(...args);
          this.addEventListener("message", (event) =>
            setTimeout(() => this.handler?.({ data: event.data }), delay),
          );
        }
        set onmessage(handler) {
          this.handler = handler;
        }
        get onmessage() {
          return this.handler;
        }
        send(data) {
          setTimeout(() => {
            if (this.readyState === 1) super.send(data);
          }, delay);
        }
      };
    }, delay);
    const page = await context.newPage();
    await page.goto(baseURL);
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#you")).toContainText("jump ready");
    await page.waitForTimeout(3000);
    const samples = [];
    for (let trial = 0; trial < 4; trial++) {
      const sample = await page.evaluate(
        () =>
          new Promise((resolve, reject) => {
            const canvas = document.getElementById("world"),
              ctx = canvas.getContext("2d");
            canvas.focus();
            function centre(region) {
              const [x, y, w, h] = region,
                d = ctx.getImageData(x, y, w, h).data;
              let sum = 0,
                n = 0;
              for (let i = 0; i < d.length; i += 4)
                if (d[i] === 255 && d[i + 1] === 56 && d[i + 2] === 105) {
                  sum += x + ((i / 4) % w);
                  n++;
                }
              return n ? sum / n : null;
            }
            const all = ctx.getImageData(0, 0, 1200, 720).data;
            let minX = 1200,
              minY = 720,
              maxX = 0,
              maxY = 0;
            for (let i = 0; i < all.length; i += 4)
              if (all[i] === 255 && all[i + 1] === 56 && all[i + 2] === 105) {
                const x = (i / 4) % 1200,
                  y = Math.floor(i / 4 / 1200);
                minX = Math.min(minX, x);
                maxX = Math.max(maxX, x);
                minY = Math.min(minY, y);
                maxY = Math.max(maxY, y);
              }
            if (minX === 1200)
              return reject(
                Error("local accent absent from actual Canvas pixels"),
              );
            const region = [
              Math.max(0, minX - 10),
              Math.max(0, minY - 10),
              Math.min(180, 1200 - Math.max(0, minX - 10)),
              Math.min(maxY - minY + 32, 720 - Math.max(0, minY - 10)),
            ];
            const before = centre(region),
              at = performance.now();
            canvas.dispatchEvent(
              new KeyboardEvent("keydown", {
                code: "ArrowRight",
                key: "ArrowRight",
                bubbles: true,
                cancelable: true,
              }),
            );
            function poll() {
              const x = centre(region),
                elapsed = performance.now() - at;
              if (x !== null && x > before + 0.3) {
                canvas.dispatchEvent(
                  new KeyboardEvent("keyup", {
                    code: "ArrowRight",
                    key: "ArrowRight",
                    bubbles: true,
                    cancelable: true,
                  }),
                );
                return resolve({
                  visible_ms: elapsed,
                  probe:
                    window.multiboxDiagnostics?.inputSamples.at(-1) || null,
                });
              }
              if (elapsed > 1500)
                return reject(Error("no visible motion within 1500ms"));
              requestAnimationFrame(poll);
            }
            requestAnimationFrame(poll);
          }),
      );
      samples.push(sample);
      await page.waitForTimeout(1000);
    }
    results.push({
      delay_each_way_ms: delay,
      samples,
      diagnostics: await page.evaluate(
        () => window.multiboxDiagnostics || null,
      ),
    });
    if (process.env.MULTIBOX_QA_DIR)
      await page.screenshot({
        path: `${process.env.MULTIBOX_QA_DIR}/latency-${delay}.png`,
      });
    await context.close();
  }
  console.log("CANVAS_LATENCY", JSON.stringify(results));
  if (process.env.MULTIBOX_QA_DIR)
    await writeFile(
      `${process.env.MULTIBOX_QA_DIR}/canvas-latency.json`,
      JSON.stringify(results, null, 2),
    );
});

test("real touch jump and HUD key focus control the game without document scroll", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage(),
    sent = [];
  page.on("websocket", (ws) =>
    ws.on("framesent", (frame) => {
      try {
        sent.push(JSON.parse(frame.payload));
      } catch {}
    }),
  );
  await page.goto(baseURL);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("#you")).toContainText("jump ready", {
    timeout: 5000,
  });
  await page.getByRole("button", { name: "Jump", exact: true }).tap();
  expect(sent.some((m) => m.jump === true)).toBe(true);
  await page.getByRole("button", { name: "Settings / disconnect" }).focus();
  await page.keyboard.down("ArrowDown");
  await expect.poll(() => sent.at(-1)?.down).toBe(true);
  await page.keyboard.up("ArrowDown");
  await expect.poll(() => sent.at(-1)?.down).toBe(false);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  await page.getByRole("button", { name: "Settings / disconnect" }).click();
  await page.locator("#nickname").fill("typing");
  await page.keyboard.press("ArrowLeft");
  expect(sent.at(-1)?.left).toBe(false);
  if (process.env.MULTIBOX_QA_DIR)
    await page.screenshot({
      path: `${process.env.MULTIBOX_QA_DIR}/settings-phone.png`,
    });
  await page.keyboard.press("Escape");
  await expect(page.locator("#world")).toBeFocused();
  await context.close();
});
