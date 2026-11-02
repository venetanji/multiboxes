import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

test("setup, play, settings and recovery across device sizes", async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(60000);
  const layouts = [];
  for (const [name, width, height, touch] of [
    ["desktop", 1440, 900, false],
    ["short", 1000, 480, false],
    ["portrait", 390, 844, true],
    ["small-phone", 320, 568, true],
    ["short-phone", 320, 480, true],
    ["landscape", 844, 390, true],
    ["small-landscape", 568, 320, true],
    ["tiny-landscape", 480, 240, true],
  ]) {
    const context = await browser.newContext({
      baseURL,
      viewport: { width, height },
      hasTouch: touch,
      isMobile: touch,
    });
    const page = await context.newPage(),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const capture = async (state) => {
      if (process.env.MULTIBOX_QA_DIR)
        await page.screenshot({
          path: `${process.env.MULTIBOX_QA_DIR}/${name}-${state}.png`,
        });
    };
    await page.goto("/");
    for (const field of ["#nickname", "#server"])
      expect(
        await page.locator(field).evaluate((input) =>
          parseFloat(getComputedStyle(input).fontSize),
        ),
      ).toBeGreaterThanOrEqual(16);
    await capture("setup");
    await page.locator("#nickname").fill("A square with a long name");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#world")).toBeFocused();
    await expect(page.locator("#you")).toContainText("jump ready");
    await page.waitForTimeout(100);
    await capture("play");
    layouts.push({
      name,
      viewport: { width, height },
      canvas: await page.locator("#world").boundingBox(),
      controls: await page.locator("[data-control]").evaluateAll((buttons) =>
        buttons.map((b) => ({
          control: b.dataset.control,
          width: b.getBoundingClientRect().width,
          height: b.getBoundingClientRect().height,
        })),
      ),
    });
    await page.getByRole("button", { name: "Settings / disconnect" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#nickname").fill("Edited name");
    await page.keyboard.press("ArrowLeft");
    await capture("settings");
    await page.getByRole("button", { name: "Resume game" }).click();
    await expect(page.locator("#world")).toBeFocused();
    await page.keyboard.down("ArrowRight");
    await page.keyboard.up("ArrowRight");
    await page.getByRole("button", { name: "Settings / disconnect" }).click();
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(page.locator("#server")).toBeVisible();
    await capture("disconnected");
    await page.locator("#server").fill("ws://127.0.0.1:9/ws");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#status")).toHaveAttribute("data-error", "true");
    await capture("error");
    const wsURL = new URL("/ws", baseURL);
    wsURL.protocol = "ws:";
    await page.locator("#server").fill(wsURL.href);
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#world")).toBeFocused();
    expect(errors).toEqual([]);
    await context.close();
  }
  if (process.env.MULTIBOX_QA_DIR)
    await writeFile(
      `${process.env.MULTIBOX_QA_DIR}/layouts.json`,
      JSON.stringify(layouts, null, 2),
    );
});
