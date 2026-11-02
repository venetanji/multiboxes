import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.mjs",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  outputDir: process.env.MULTIBOX_QA_DIR
    ? `${process.env.MULTIBOX_QA_DIR}/browser-results`
    : "../../test-results",
  reporter: [["list"]],
  use: {
    baseURL: process.env.MULTIBOX_URL || "http://localhost:8000",
    channel: "chromium",
    launchOptions: {
      chromiumSandbox: true,
      args: ["--disable-setuid-sandbox"],
    },
    viewport: { width: 1440, height: 1120 },
  },
});
