import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Model", exact: true }),
  ).toHaveValue("Local steady");
}
async function collapsePreference(page: Page) {
  await page.getByText("Options", { exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Collapse after sending on this device" })
    .check();
  await page.getByText("Options", { exact: true }).click();
}
function countGenerations(page: Page) {
  const posts: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/runs"
    )
      posts.push(request.postData()!);
  });
  return posts;
}

test("Pixel model search and privacy do not dispatch; long answers retain reading space", async ({
  page,
}) => {
  const posts = countGenerations(page);
  await page.route("**/api/models", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.models.push({
      ...data.models[0],
      id: "mock/nemotron",
      name: "NVIDIA: Nemotron 3 Ultra (free)",
    });
    await route.fulfill({ response, json: data });
  });
  await signIn(page);
  const mode = page.getByLabel("Mode", { exact: true });
  await expect(mode).toHaveCSS("font-size", "16px");
  await expect(mode.locator("option").first()).toHaveCSS("font-size", "18px");
  expect((await mode.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const picker = page.getByRole("combobox", { name: "Model", exact: true });
  await picker.fill("NeMoTrOn");
  const choices = page
    .getByRole("listbox", { name: "Model", exact: true })
    .getByRole("option");
  await expect(choices).toHaveCount(1);
  await expect(choices).toContainText("NVIDIA");
  await picker.press("Escape");
  await expect(picker).toHaveValue("Local steady");
  await picker.fill("mock/nemotron");
  await picker.press("Enter");
  await expect(picker).toHaveValue("Nemotron 3 Ultra (free)");
  await picker.fill("steady");
  await page.getByRole("option", { name: /Local steady/ }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  const privacy = page.getByRole("region", { name: "Privacy" });
  await expect(privacy).toBeInViewport();
  await expect(privacy).toContainText("Simulated provider");
  await page.getByRole("button", { name: "Close navigation" }).click();
  expect(posts).toHaveLength(0);
  const text = Array.from(
    { length: 6 },
    (_, i) =>
      `### Pixel reading section ${i + 1}\n\nLong answers need enough space for comfortable reading. This synthetic paragraph tests the response area without contacting an external provider.`,
  ).join("\n\n");
  await page.getByLabel("Message", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toBeVisible({ timeout: 15000 });
  const reading = await page.locator(".chat-scroll").boundingBox();
  expect(reading!.height).toBeGreaterThan(650);
  await expect(page.locator(".response-details")).not.toHaveAttribute("open");
  await expect(
    page.getByText("Actual cost: $0.000000", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(posts).toHaveLength(1);
  await page.screenshot({
    path: "../artifacts/mobile-compact-pixel.png",
    fullPage: true,
  });
  await test.info().attach("reading-area", {
    body: JSON.stringify({
      viewport: { width: 412, height: 924 },
      height: reading!.height,
    }),
    contentType: "application/json",
  });
});

test("accepted sending folds, keeps Stop, and restores preference/history without folding failed drafts", async ({
  page,
}) => {
  const posts = countGenerations(page);
  await signIn(page);
  await collapsePreference(page);
  const prompt =
    "Pixel collapse persistence. " +
    "A synthetic streaming sentence for cancellation and recovery. ".repeat(24);
  const input = page.getByLabel("Message", { exact: true });
  await input.fill(prompt);
  await input.press("Enter");
  await expect(
    page.getByRole("button", { name: "Write a message" }),
  ).toBeInViewport();
  const stop = page.getByRole("button", {
    name: "Stop generation",
    exact: true,
  });
  await expect(stop).toBeInViewport();
  const readingArea = page.locator(".chat-scroll");
  const output = page.locator(".answer .markdown");
  await expect
    .poll(async () => (await output.textContent())?.length ?? 0)
    .toBeGreaterThan(40);
  await readingArea.hover();
  await page.mouse.wheel(0, -10000);
  await expect.poll(() => readingArea.evaluate((el) => el.scrollTop)).toBe(0);
  const length = (await output.textContent())!.length;
  await expect
    .poll(async () => (await output.textContent())!.length)
    .toBeGreaterThan(length + 24);
  expect(await readingArea.evaluate((el) => el.scrollTop)).toBe(0);
  await stop.click();
  await expect(
    page.getByRole("status").filter({ hasText: "Cancelled" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Write a message" }).click();
  await expect(input).toBeFocused();
  await input.fill("Recoverable draft");
  await page.getByRole("button", { name: "Hide composer" }).click();
  await page.getByRole("button", { name: "Continue draft" }).click();
  await expect(input).toHaveValue("Recoverable draft");
  await input.fill("");
  await page.reload();
  await expect(input).toBeVisible();
  await page.getByText("Options", { exact: true }).click();
  await expect(
    page.getByRole("checkbox", {
      name: "Collapse after sending on this device",
    }),
  ).toBeChecked();
  await page.getByText("Options", { exact: true }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation", { name: "Search history" })
    .getByRole("button", { name: prompt.slice(0, 80), exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Write a message" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(input).toBeVisible();
  await page.setViewportSize({ width: 412, height: 924 });
  await page.getByRole("button", { name: "Write a message" }).click();
  await page.route("**/api/runs", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "Synthetic rejected submission" } },
    }),
  );
  await input.fill("Keep after failure");
  await input.press("Shift+Enter");
  await input.dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true,
  });
  expect(posts).toHaveLength(1);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "Synthetic rejected submission",
  );
  await expect(input).toBeVisible();
  await expect(input).toHaveValue("Keep after failure\n");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect.poll(() => posts.length).toBe(3);
  expect(JSON.parse(posts[1]).idempotency_key).toBe(
    JSON.parse(posts[2]).idempotency_key,
  );
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([
    "lab-chatbot.mobile-collapse",
  ]);
});

test("compact uploads preserve existing files and the draft after a rejected upload", async ({
  page,
}) => {
  const posts = countGenerations(page);
  await signIn(page);
  const input = page.getByLabel("Message", { exact: true });
  await input.fill("Keep my draft and attachments");
  const upload = page.getByLabel("Attach files to chat");
  await upload.setInputFiles({
    name: "valid-mobile.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Synthetic local attachment"),
  });
  await expect(
    page
      .locator(".compact-picker")
      .getByText("valid-mobile.txt", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/attachments", (route) =>
    route.fulfill({
      status: 413,
      json: { error: { message: "Synthetic upload rejection" } },
    }),
  );
  await upload.setInputFiles({
    name: "rejected-mobile.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Rejected fixture"),
  });
  await expect(page.getByRole("alert")).toHaveText(
    "Synthetic upload rejection",
  );
  await expect(input).toHaveValue("Keep my draft and attachments");
  await expect(
    page
      .locator(".compact-picker")
      .getByText("valid-mobile.txt", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeInViewport();
  await page.getByText("Options", { exact: true }).click();
  await expect(
    page
      .locator(".compact-picker")
      .getByText("5 files · 10 MiB / file · 25 MiB total", { exact: true }),
  ).toBeVisible();
  await page.getByText("Options", { exact: true }).click();
  expect(posts).toHaveLength(0);
  const firstReply = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/runs",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const firstRun = await (await firstReply).json();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Edit as a new run" }).click();
  await expect(upload).toBeDisabled();
  await input.fill("Edited attachment fixture");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(2);
  await expect(
    page
      .locator(".answer .attachment-item strong")
      .filter({ hasText: "valid-mobile.txt" }),
  ).toHaveCount(2);
  expect(JSON.parse(posts[1])).toMatchObject({
    retry_of: firstRun.id,
    prompt: "Edited attachment fixture",
    attachment_ids: [],
  });
  for (const size of [
    { width: 360, height: 430 },
    { width: 924, height: 412 },
  ]) {
    await page.setViewportSize(size);
    await expect(
      page.getByRole("button", { name: "Send message", exact: true }),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
