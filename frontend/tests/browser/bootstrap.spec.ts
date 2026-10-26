import { expect, test } from "@playwright/test";

test("authenticated local preview, reload and logout work on desktop and mobile", async ({
  page,
}, info) => {
  await page.goto("/");
  await expect(page.getByLabel("Owner passphrase")).toBeVisible();
  await page.screenshot({
    path: `../artifacts/m1-login-${info.project.name}.png`,
    fullPage: true,
  });
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Preview prompt").fill("A deliberate experiment");
  await page.getByRole("button", { name: /Run preview/ }).click();
  await expect(
    page.getByText("Local preview: A deliberate experiment"),
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
    path: `../artifacts/m1-${info.project.name}.png`,
    fullPage: true,
  });
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(
      page.getByRole("complementary", { name: "Navigation" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close navigation" }).click();
  }
  await page.reload();
  await expect(page.getByLabel("Preview prompt")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Owner passphrase")).toBeVisible();
  expect((await page.request.get("/api/runs/private/events")).status()).toBe(
    401,
  );
});
