const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/browser",
  timeout: 45000,
  expect: { timeout: 15000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:8765/slaymusic/",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: [["list"], ["html", { open: "never" }]],
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", viewport: { width: 1440, height: 1100 } },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command:
          ".venv/bin/python -m uvicorn app_final:app --host 127.0.0.1 --port 8765 --no-access-log",
        env: { APP_BASE_PATH: "/slaymusic" },
        url: "http://127.0.0.1:8765/slaymusic/health",
        reuseExistingServer: !process.env.CI,
        timeout: 30000,
      },
});
