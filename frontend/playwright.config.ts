import { defineConfig, devices } from "@playwright/test";

const apiPort = Number(process.env.LAB_BROWSER_API_PORT ?? "8000");
const uiPort = Number(process.env.LAB_BROWSER_UI_PORT ?? "5173");

export default defineConfig({
  testDir: "./tests/browser",
  use: { baseURL: `http://127.0.0.1:${uiPort}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 360, height: 740 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: "../backend/.venv/bin/python ../scripts/browser-backend.py",
      url: `http://127.0.0.1:${apiPort}/api/health/live`,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --port ${uiPort} --strictPort`,
      url: `http://127.0.0.1:${uiPort}`,
      reuseExistingServer: false,
    },
  ],
});
