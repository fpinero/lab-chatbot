import { expect, test } from "@playwright/test";

test("authenticated streaming chat, saved history, model repeat and logout", async ({
  page,
}, info) => {
  const prompt = `A deliberate experiment ${info.project.name}`;
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Model", { exact: true })).toHaveValue(
    "mock/steady",
  );
  await page.getByLabel("Message", { exact: true }).fill(prompt);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "This is a deterministic mock response. No credits were spent.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await page.screenshot({
    path: `../artifacts/m2-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByLabel("Model", { exact: true }).selectOption("mock/clear");
  await page
    .getByRole("button", { name: "Repeat with selected model" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(2);
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(
      page.getByRole("complementary", { name: "Navigation" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close navigation" }).click();
  }
  await page.reload();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation", { name: "Search history" })
    .getByRole("button", { name: prompt, exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Owner passphrase")).toBeVisible();
  expect((await page.request.get("/api/runs/private/events")).status()).toBe(
    401,
  );
});

test("composer remains usable at a reduced mobile viewport", async ({
  page,
}, info) => {
  test.skip(
    info.project.name !== "mobile",
    "Reduced viewport is a mobile-only scenario.",
  );
  await page.setViewportSize({ width: 360, height: 430 });
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("Small viewport");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toBeAttached();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/m2-mobile-keyboard.png",
    fullPage: true,
  });
});

test("attachments and independent comparison cards survive reload and continue into chat", async ({
  page,
}, info) => {
  const prompt = `Comparison fixture ${info.project.name}`;
  let dispatches = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      ["/api/runs", "/api/comparisons"].includes(
        new URL(request.url()).pathname,
      )
    )
      dispatches += 1;
  });
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByLabel("Message", { exact: true })
    .fill(`Unsent chat ${info.project.name}`);
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  const panel = page.getByRole("region", { name: "Compare", exact: true });
  await panel.getByLabel("Comparison prompt").fill(prompt);
  const image = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 200;
    canvas.height = 120;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#325c49";
    context.fillRect(0, 0, 200, 120);
    context.fillStyle = "#fff";
    context.font = "18px sans-serif";
    context.fillText("Local fixture", 24, 68);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await panel.getByLabel("Attach files to comparison").setInputFiles([
    {
      name: `fixture-${info.project.name}.png`,
      mimeType: "image/png",
      buffer: Buffer.from(image, "base64"),
    },
    {
      name: `fixture-${info.project.name}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from("Local document fixture"),
    },
  ]);
  await expect(
    panel.getByText(`fixture-${info.project.name}.txt`, { exact: true }),
  ).toBeVisible();
  await panel.getByLabel("Local brief", { exact: true }).check();
  await page.getByLabel("Mode", { exact: true }).selectOption("chat");
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
    `Unsent chat ${info.project.name}`,
  );
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  await expect(panel.getByLabel("Comparison prompt")).toHaveValue(prompt);
  await expect(
    panel.getByText(`fixture-${info.project.name}.png`, { exact: true }),
  ).toBeVisible();
  expect(dispatches).toBe(0);
  await panel
    .getByRole("button", { name: "Compare models", exact: true })
    .click();
  const results = panel.locator(".comparison-results");
  await expect(
    results.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(3);
  expect(dispatches).toBe(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../artifacts/m3-compare-${info.project.name}.png`,
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByLabel("Mode", { exact: true })).toBeVisible();
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation", { name: "Search history" })
    .getByRole("button", { name: prompt, exact: true })
    .click();
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  await expect(
    results.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(3);
  await results
    .getByRole("article")
    .first()
    .getByRole("button", { name: "Continue with this answer", exact: true })
    .click();
  await expect(page.getByLabel("Mode", { exact: true })).toHaveValue("chat");
  await expect(
    page.getByText(/Its original cost is already accounted for/),
  ).toBeVisible();
  expect(dispatches).toBe(1);
  await page.screenshot({
    path: `../artifacts/m3-continued-${info.project.name}.png`,
    fullPage: true,
  });
});
