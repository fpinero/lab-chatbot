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
