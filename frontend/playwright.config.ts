import { defineConfig, devices } from "@playwright/test";

const apiPort = Number(process.env.LAB_BROWSER_API_PORT ?? "8000");
const uiPort = Number(process.env.LAB_BROWSER_UI_PORT ?? "5173");
const instances = ["desktop", "mobile", "pixel-10"].map((name, index) => ({
  name,
  apiPort: apiPort + index * 10,
  uiPort: uiPort + index * 10,
}));

export default defineConfig({
  testDir: "./tests/browser",
  use: { trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop",
      testIgnore: "**/mobile-ux.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: `http://127.0.0.1:${instances[0].uiPort}`,
      },
    },
    {
      name: "mobile",
      testIgnore: "**/mobile-ux.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 360, height: 740 },
        isMobile: true,
        hasTouch: true,
        baseURL: `http://127.0.0.1:${instances[1].uiPort}`,
      },
    },
    {
      name: "pixel-10",
      testMatch: "**/mobile-ux.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 412, height: 924 },
        isMobile: true,
        hasTouch: true,
        baseURL: `http://127.0.0.1:${instances[2].uiPort}`,
      },
    },
  ],
  // Each device project has its own data, sessions, queue and rate window.
  webServer: instances.flatMap((instance) => [
    {
      command: "../backend/.venv/bin/python ../scripts/browser-backend.py",
      env: {
        LAB_BROWSER_API_PORT: String(instance.apiPort),
        LAB_BROWSER_UI_PORT: String(instance.uiPort),
      },
      url: `http://127.0.0.1:${instance.apiPort}/api/health/live`,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --port ${instance.uiPort} --strictPort`,
      env: {
        LAB_BROWSER_API_PORT: String(instance.apiPort),
        LAB_BROWSER_UI_PORT: String(instance.uiPort),
      },
      url: `http://127.0.0.1:${instance.uiPort}`,
      reuseExistingServer: false,
    },
  ]),
});
