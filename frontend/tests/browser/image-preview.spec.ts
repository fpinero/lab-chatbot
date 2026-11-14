import { expect, test, type Page } from "@playwright/test";
import type { RunInfo } from "../../src/lib/api";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
}

async function previewPng(page: Page) {
  return Buffer.from(
    await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 1600;
      canvas.height = 1200;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#f8f7ed";
      ctx.fillRect(0, 0, 1600, 1200);
      ctx.fillStyle = "#325c49";
      ctx.font = "bold 64px sans-serif";
      ctx.fillText("Synthetic screenshot preview", 80, 130);
      for (let row = 0; row < 10; row++)
        ctx.fillText(`Readable detail ${row + 1}`, 80, 250 + row * 80);
      return canvas.toDataURL("image/png").split(",")[1];
    }),
    "base64",
  );
}

test("draft image previews fit, zoom, scroll and dismiss without changing inputs or dispatching", async ({
  page,
}, info) => {
  await signIn(page);
  const calls: string[] = [];
  page.on("request", (request) => {
    if (["POST", "DELETE"].includes(request.method()))
      calls.push(new URL(request.url()).pathname);
  });
  const buffer = await previewPng(page);
  await page
    .getByLabel("Message", { exact: true })
    .fill("Preserve this prompt while checking the screenshot");
  await page.getByLabel("Attach files to chat", { exact: true }).setInputFiles([
    { name: "first-preview.png", mimeType: "image/png", buffer },
    { name: "second-preview.png", mimeType: "image/png", buffer },
  ]);
  const picker = page.locator(".compact-picker");
  await expect(picker.locator(".attachment-item")).toHaveCount(2);
  const beforeCalls = [...calls];
  await page.evaluate(() => {
    const policy = document.createElement("meta");
    policy.httpEquiv = "Content-Security-Policy";
    policy.content = "style-src 'self'";
    document.head.append(policy);
  });
  const opener = picker.getByRole("button", {
    name: "Preview image: first-preview.png",
    exact: true,
  });
  const originalSource = await opener.locator("img").getAttribute("src");
  await opener.focus();
  await opener.press("Enter");
  const dialog = page.getByRole("dialog", {
    name: "first-preview.png",
    exact: true,
  });
  const close = dialog.getByRole("button", {
    name: "Close image preview",
    exact: true,
  });
  const photo = dialog.getByRole("img", {
    name: "first-preview.png",
    exact: true,
  });
  const viewport = dialog.getByRole("region", {
    name: "Image preview area",
    exact: true,
  });
  await expect(photo).toBeVisible();
  expect(await dialog.evaluate((element) => element.matches(":modal"))).toBe(
    true,
  );
  await expect(close).toBeFocused();
  await expect(photo).toHaveAttribute("src", originalSource!);
  expect((await photo.boundingBox())!.width).toBeGreaterThan(144);
  await close.press("Shift+Tab");
  await expect(viewport).toBeFocused();
  await viewport.press("Tab");
  await expect(close).toBeFocused();
  await dialog
    .getByRole("button", { name: "Actual size", exact: true })
    .click();
  await expect(dialog.getByLabel("Zoom level")).toHaveText("100%");
  await expect.poll(async () => (await photo.boundingBox())!.width).toBe(1600);
  expect(
    await viewport.evaluate(
      (element) =>
        element.scrollWidth > element.clientWidth &&
        element.scrollHeight > element.clientHeight,
    ),
  ).toBe(true);
  await viewport.evaluate((element) => {
    element.scrollLeft = 80;
    element.scrollTop = 120;
  });
  expect(
    await viewport.evaluate((element) => ({
      x: element.scrollLeft,
      y: element.scrollTop,
    })),
  ).toEqual({ x: 80, y: 120 });
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(dialog.getByLabel("Zoom level")).toHaveText("150%");
  await dialog.getByRole("button", { name: "Zoom out", exact: true }).click();
  await expect(dialog.getByLabel("Zoom level")).toHaveText("100%");
  await dialog
    .getByRole("button", { name: "Fit to screen", exact: true })
    .click();
  expect((await photo.boundingBox())!.width).toBeLessThanOrEqual(
    (await viewport.boundingBox())!.width,
  );
  if (info.project.use.hasTouch)
    await page.setViewportSize({ width: 360, height: 430 });
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    const box = (await dialog.locator(".image-preview-panel").boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
    expect((await close.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await page.screenshot({
      path: `../artifacts/attachment-preview-${info.project.name}-${scheme}.png`,
    });
  }
  const point = (await photo.boundingBox())!;
  await page.mouse.move(point.x + point.width / 2, point.y + point.height / 2);
  await page.mouse.down();
  await page.mouse.move(3, 3);
  await page.mouse.up();
  await expect(dialog).toBeVisible();
  await page.mouse.click(3, 3);
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  const second = picker.getByRole("button", {
    name: "Preview image: second-preview.png",
    exact: true,
  });
  await second.click();
  const secondDialog = page.getByRole("dialog", {
    name: "second-preview.png",
    exact: true,
  });
  await expect(
    secondDialog.getByRole("img", { name: "second-preview.png", exact: true }),
  ).toBeVisible();
  await secondDialog
    .getByRole("button", { name: "Close image preview", exact: true })
    .press("Escape");
  await expect(secondDialog).toHaveCount(0);
  await expect(second).toBeFocused();
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
    "Preserve this prompt while checking the screenshot",
  );
  await expect(picker.locator(".attachment-item")).toHaveCount(2);
  expect(calls).toEqual(beforeCalls);
});

test("stored image previews survive history reload and preserve draft, scroll and private access", async ({
  page,
}, info) => {
  await signIn(page);
  let generations = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/runs"
    )
      generations++;
  });
  const buffer = await previewPng(page);
  const name = `history-preview-${info.project.name}.png`;
  const prompt = `Preview history ${info.project.name} ${"Synthetic screenshot context for reading. ".repeat(24)}`;
  const input = page.getByLabel("Message", { exact: true });
  await input.fill(prompt);
  await page
    .getByLabel("Attach files to chat", { exact: true })
    .setInputFiles({ name, mimeType: "image/png", buffer });
  const accepted = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/runs",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const run: RunInfo = await (await accepted).json();
  await expect(
    page
      .locator(".answer")
      .last()
      .getByRole("status")
      .filter({ hasText: "Completed" }),
  ).toBeVisible();
  const saved = await (
    await page.request.get(`/api/conversations/${run.conversation_id}`)
  ).json();
  await input.fill("Keep this new unsent draft");
  await page.getByLabel("Attach files to chat", { exact: true }).setInputFiles({
    name: "unrelated-draft.png",
    mimeType: "image/png",
    buffer,
  });
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(1);
  const opener = page
    .locator(".answer")
    .getByRole("button", { name: `Preview image: ${name}`, exact: true });
  await opener.scrollIntoViewIfNeeded();
  const scroll = page.getByRole("region", {
    name: "Conversation",
    exact: true,
  });
  const before = await scroll.evaluate((element) => element.scrollTop);
  const source = await opener.locator("img").getAttribute("src");
  await opener.click();
  const dialog = page.getByRole("dialog", { name, exact: true });
  await expect(dialog.getByRole("img", { name, exact: true })).toHaveAttribute(
    "src",
    source!,
  );
  await scroll.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await dialog
    .getByRole("button", { name: "Close image preview", exact: true })
    .click();
  await expect(opener).toBeFocused();
  expect(await scroll.evaluate((element) => element.scrollTop)).toBeCloseTo(
    before,
    0,
  );
  await expect(input).toHaveValue("Keep this new unsent draft");
  await expect(
    page.locator(".compact-picker .attachment-item strong"),
  ).toHaveText("unrelated-draft.png");
  await page.reload();
  await expect(input).toBeVisible();
  if (info.project.use.hasTouch)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation", { name: "Search history", exact: true })
    .getByRole("button", { name: prompt.slice(0, 80), exact: true })
    .click();
  await opener.click();
  await expect(dialog.getByRole("img", { name, exact: true })).toBeVisible();
  const response = await page.request.get(source!);
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toContain("no-store");
  const anonymous = await page.context().browser()!.newContext();
  try {
    const denied = await anonymous.request.get(
      new URL(source!, page.url()).href,
    );
    expect(denied.status()).toBe(401);
  } finally {
    await anonymous.close();
  }
  await dialog
    .getByRole("button", { name: "Close image preview", exact: true })
    .press("Escape");
  expect(
    (
      await (
        await page.request.get(`/api/conversations/${run.conversation_id}`)
      ).json()
    ).runs,
  ).toEqual(saved.runs);
  expect(generations).toBe(1);
});
