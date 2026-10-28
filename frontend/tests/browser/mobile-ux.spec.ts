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

test("copying a saved prompt preserves the new draft and image until explicit sending", async ({
  page,
}) => {
  const posts = countGenerations(page);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page);
  const prompt = "Describe this image.\n\nKeep the blank line.";
  const input = page.getByLabel("Message", { exact: true });
  const upload = page.getByLabel("Attach files to chat");
  const image = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 120;
    canvas.height = 80;
    canvas.getContext("2d")!.fillRect(0, 0, 120, 80);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await input.fill(prompt);
  await upload.setInputFiles({
    name: "first-image.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  await input.fill("Keep this unsent draft");
  await upload.setInputFiles({
    name: "second-image.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(1);
  const copyPrompt = page.getByRole("button", {
    name: "Copy prompt",
    exact: true,
  });
  await copyPrompt.click();
  await expect(copyPrompt).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    prompt,
  );
  await expect(input).toHaveValue("Keep this unsent draft");
  await expect(
    page
      .locator(".compact-picker")
      .getByText("second-image.png", { exact: true }),
  ).toBeVisible();
  expect(posts).toHaveLength(1);
  expect((await copyPrompt.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({
    path: "../artifacts/copy-prompt-pixel.png",
    fullPage: true,
  });
  await input.fill(await page.evaluate(() => navigator.clipboard.readText()));
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(2);
  expect(posts).toHaveLength(2);
  const original = JSON.parse(posts[0]);
  const reused = JSON.parse(posts[1]);
  expect(reused.prompt).toBe(prompt);
  expect(reused.attachment_ids).toHaveLength(1);
  expect(reused.attachment_ids).not.toEqual(original.attachment_ids);
  expect(reused.retry_of).toBeUndefined();
});

test("New conversation clears failed mobile input, attachment, options and errors before a fresh send", async ({
  page,
}) => {
  const posts = countGenerations(page);
  await signIn(page);
  const input = page.getByLabel("Message", { exact: true });
  await input.fill("Previous failed prompt");
  await page.getByLabel("Attach files to chat").setInputFiles({
    name: "old-draft.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Old private context"),
  });
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(1);
  await page.getByText("Options", { exact: true }).click();
  await page
    .locator(".compact-picker")
    .getByLabel("System prompt", { exact: true })
    .fill("Old system context");
  await page
    .locator(".compact-picker")
    .getByLabel("Maximum output tokens", { exact: true })
    .fill("64");
  await page.getByText("Options", { exact: true }).click();
  await page.route("**/api/runs", (route) =>
    route.fulfill({
      status: 402,
      json: {
        error: {
          message:
            "The request and outstanding reservations exceed the OpenRouter key remainder.",
        },
      },
    }),
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "outstanding reservations",
  );
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(input).toHaveValue("");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeDisabled();
  await page.getByText("Options", { exact: true }).click();
  await expect(
    page
      .locator(".compact-picker")
      .getByLabel("System prompt", { exact: true }),
  ).toHaveValue("");
  await expect(
    page
      .locator(".compact-picker")
      .getByLabel("Maximum output tokens", { exact: true }),
  ).toHaveValue("2048");
  await page.getByText("Options", { exact: true }).click();
  expect(posts).toHaveLength(1);
  await page.screenshot({
    path: "../artifacts/new-conversation-clean-pixel.png",
    fullPage: true,
  });
  await page.unroute("**/api/runs");
  await input.fill("Fresh prompt without the old attachment");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  expect(posts).toHaveLength(2);
  const old = JSON.parse(posts[0]),
    fresh = JSON.parse(posts[1]);
  expect(fresh.conversation_id).not.toBe(old.conversation_id);
  expect(fresh.idempotency_key).not.toBe(old.idempotency_key);
  expect(fresh).toMatchObject({
    system_prompt: "",
    attachment_ids: [],
    max_tokens: 2048,
  });
});

test("mobile sidebar balance refresh receives taps, reports failure and survives drawer reopen", async ({
  page,
}) => {
  const posts = countGenerations(page);
  let reads = 0,
    failNext = false,
    holdNext = false;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(/\/api\/usage(?:\?.*)?$/, async (route) => {
    reads += 1;
    if (holdNext) {
      holdNext = false;
      await gate;
    }
    if (failNext) {
      failNext = false;
      await route.fulfill({
        status: 503,
        json: { error: { message: "Temporary provider read failure" } },
      });
      return;
    }
    await route.fulfill({
      json: {
        spend_control: "provider",
        simulated: false,
        provider_key_budget: {
          limit_usd: "9.9",
          remaining_usd: "9.8",
          used_usd: "0.1",
          checked_at: 1700000000 + reads * 60,
        },
        daily_actual_microusd: 100000,
        outstanding_microusd: 9800000,
        uncertain_count: 1,
        conversations: {},
        request_limit_microusd: null,
        daily_limit_microusd: null,
      },
    });
  });
  await signIn(page);
  await page.getByRole("button", { name: "Open navigation" }).tap();
  const usage = page.getByRole("region", { name: "Usage", exact: true });
  const button = usage.getByRole("button", {
    name: "Refresh balance",
    exact: true,
  });
  for (const size of [
    { width: 412, height: 924 },
    { width: 360, height: 430 },
  ]) {
    await page.setViewportSize(size);
    await button.scrollIntoViewIfNeeded();
    const before = await usage.locator("small").textContent();
    const previous = reads;
    await button.tap();
    await expect.poll(() => reads).toBe(previous + 1);
    await expect(usage.locator("small")).not.toHaveText(before!);
    await expect(usage.getByRole("status")).toHaveText("Balance updated.");
  }
  await page.setViewportSize({ width: 412, height: 924 });
  holdNext = true;
  const previous = reads;
  await button.tap();
  await expect(button).toBeDisabled();
  await expect(button).toHaveText("Refreshing balance...");
  await page.getByRole("button", { name: "Close navigation" }).tap();
  await page.getByRole("button", { name: "Open navigation" }).tap();
  await expect(button).toBeDisabled();
  expect(reads).toBe(previous + 1);
  release();
  await expect(button).toBeEnabled();
  await expect(usage.getByRole("status")).toHaveText("Balance updated.");
  await button.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../artifacts/mobile-balance-refresh.png",
    fullPage: true,
  });
  const time = await usage.locator("small").textContent();
  failNext = true;
  await button.tap();
  await expect(usage.getByRole("alert")).toContainText(
    "Could not refresh balance.",
  );
  await expect(usage.locator("small")).toHaveText(time!);
  await expect(button).toBeEnabled();
  await button.tap();
  await expect(usage.getByRole("alert")).toHaveCount(0);
  await expect(usage.getByRole("status")).toHaveText("Balance updated.");
  expect(posts).toHaveLength(0);
});
